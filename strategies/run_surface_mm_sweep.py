from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path

import pandas as pd

from reports.manifest import write_experiment_manifest
from reports.proof import ProofReport, ProofThresholds, write_proof_report
from reports.quote_risk import (
    quote_risk_review_check,
    quote_risk_review_parameters,
    read_quote_risk_summary,
)
from strategies.run_surface_mm_replay import SurfaceMMReplayConfig, run_surface_mm_replay


@dataclass(frozen=True)
class SurfaceMMSweepResult:
    runs: pd.DataFrame
    summary: pd.DataFrame
    proof: ProofReport
    output_dir: Path | None = None


def run_surface_mm_sweep(
    *,
    quotes_path: str | Path,
    chain_path: str | Path,
    output_dir: str | Path,
    quote_ttl_ns_values: list[int],
    order_latency_us_values: list[float],
    fill_depth_fraction_values: list[float],
    markout_horizon_ns_values: list[int],
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    contract_multiplier: float = 1.0,
    max_quotes: int | None = None,
    proof_thresholds: ProofThresholds | None = None,
    quote_risk_review_dir: str | Path | None = None,
    require_quote_risk_review: bool = False,
) -> SurfaceMMSweepResult:
    if not quote_ttl_ns_values:
        raise ValueError("quote_ttl_ns_values must not be empty")
    if not order_latency_us_values:
        raise ValueError("order_latency_us_values must not be empty")
    if not fill_depth_fraction_values:
        raise ValueError("fill_depth_fraction_values must not be empty")
    if not markout_horizon_ns_values:
        raise ValueError("markout_horizon_ns_values must not be empty")

    out = Path(output_dir)
    runs_root = out / "runs"
    runs_root.mkdir(parents=True, exist_ok=True)
    quote_risk_summary = read_quote_risk_summary(quote_risk_review_dir)
    quote_risk_check = quote_risk_review_check(
        quote_risk_summary,
        required=require_quote_risk_review,
        input_dir=quote_risk_review_dir,
    )
    parameters = {
        "quote_ttl_ns_values": quote_ttl_ns_values,
        "order_latency_us_values": order_latency_us_values,
        "fill_depth_fraction_values": fill_depth_fraction_values,
        "markout_horizon_ns_values": markout_horizon_ns_values,
        "timestamp_unit": timestamp_unit,
        "timestamp_tz": timestamp_tz,
        "filter_session": filter_session,
        "lot_size": lot_size,
        "option_tick": option_tick,
        "contract_multiplier": contract_multiplier,
        "max_quotes": max_quotes,
        "proof_thresholds": asdict(proof_thresholds) if proof_thresholds is not None else None,
        "require_quote_risk_review": bool(require_quote_risk_review),
        "quote_risk_review": quote_risk_review_parameters(quote_risk_summary, quote_risk_review_dir),
    }
    inputs = _manifest_inputs(quotes_path, chain_path, quote_risk_review_dir)

    if quote_risk_check is not None and not bool(quote_risk_check["passed"]):
        runs = _empty_sweep_runs()
        proof = _write_blocked_proof(out / "proof", quote_risk_check)
        summary = _blocked_sweep_summary(quote_risk_check, required=require_quote_risk_review)
        runs.to_csv(out / "sweep_runs.csv", index=False)
        summary.to_csv(out / "sweep_summary.csv", index=False)
        write_experiment_manifest(
            out,
            run_type="surface_mm_sweep",
            inputs=inputs,
            parameters=parameters,
        )
        return SurfaceMMSweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)

    rows = []
    run_dirs: list[Path] = []
    run_names: list[str] = []
    for quote_ttl_ns, order_latency_us, fill_depth_fraction, markout_horizon_ns in product(
        quote_ttl_ns_values,
        order_latency_us_values,
        fill_depth_fraction_values,
        markout_horizon_ns_values,
    ):
        run_name = _run_name(quote_ttl_ns, order_latency_us, fill_depth_fraction, markout_horizon_ns)
        run_dir = runs_root / run_name
        replay = run_surface_mm_replay(
            quotes_path=quotes_path,
            chain_path=chain_path,
            output_dir=run_dir,
            timestamp_unit=timestamp_unit,
            timestamp_tz=timestamp_tz,
            filter_session=filter_session,
            config=SurfaceMMReplayConfig(
                quote_ttl_ns=quote_ttl_ns,
                order_latency_us=order_latency_us,
                fill_depth_fraction=fill_depth_fraction,
                markout_horizon_ns=markout_horizon_ns,
                lot_size=lot_size,
                option_tick=option_tick,
                contract_multiplier=contract_multiplier,
                max_quotes=max_quotes,
            ),
        )
        summary = replay.summary.iloc[0].to_dict()
        rows.append(
            {
                "run": run_name,
                "run_dir": str(run_dir),
                "quote_ttl_ns": int(quote_ttl_ns),
                "order_latency_us": float(order_latency_us),
                "fill_depth_fraction": float(fill_depth_fraction),
                "markout_horizon_ns": int(markout_horizon_ns),
                "quote_count": int(len(replay.summary) and replay.summary.iloc[0]["orders_sent"]),
                "unfilled_reason_count": int(replay.unfilled["unfilled_reason"].nunique()) if not replay.unfilled.empty else 0,
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
    summary = _attach_quote_risk_summary(
        summary,
        quote_risk_check=quote_risk_check,
        required=require_quote_risk_review,
    )
    runs.to_csv(out / "sweep_runs.csv", index=False)
    summary.to_csv(out / "sweep_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="surface_mm_sweep",
        inputs=inputs,
        parameters=parameters,
    )
    return SurfaceMMSweepResult(runs=runs, summary=summary, proof=proof, output_dir=out)


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
                "median_fill_rate",
                "min_fill_rate",
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
                "median_fill_rate": float(runs["fill_rate"].median()),
                "min_fill_rate": float(runs["fill_rate"].min()),
            }
        ]
    )


def _empty_sweep_runs() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "run",
            "run_dir",
            "quote_ttl_ns",
            "order_latency_us",
            "fill_depth_fraction",
            "markout_horizon_ns",
            "quote_count",
            "unfilled_reason_count",
            "net_pnl",
            "fills",
            "proof_passed",
            "robust_score",
        ]
    )


def _blocked_sweep_summary(check: dict, *, required: bool) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "scenario_count": 0,
                "passed_scenarios": 0,
                "pass_rate": 0.0,
                "best_run": "",
                "best_robust_score": 0.0,
                "median_net_pnl": 0.0,
                "min_net_pnl": 0.0,
                "worst_drawdown": 0.0,
                "median_fill_rate": 0.0,
                "min_fill_rate": 0.0,
                "quote_risk_review_required": bool(required),
                "quote_risk_review_provided": bool(check.get("input_dir", "")),
                "quote_risk_review_passed": False,
                "quote_risk_review_reason": str(check.get("reason", "")),
            }
        ]
    )


def _attach_quote_risk_summary(
    summary: pd.DataFrame,
    *,
    quote_risk_check: dict | None,
    required: bool,
) -> pd.DataFrame:
    out = summary.copy()
    passed = True if quote_risk_check is None else bool(quote_risk_check["passed"])
    out["quote_risk_review_required"] = bool(required)
    out["quote_risk_review_provided"] = bool(quote_risk_check is not None and quote_risk_check["input_dir"])
    out["quote_risk_review_passed"] = bool(passed)
    out["quote_risk_review_reason"] = "" if quote_risk_check is None else str(quote_risk_check["reason"])
    return out


def _write_blocked_proof(output_dir: Path, check: dict) -> ProofReport:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    metrics = pd.DataFrame(
        columns=[
            "run",
            "net_pnl",
            "fills",
            "turnover",
            "total_costs",
            "cost_bps",
            "pnl_per_fill",
            "maker_share",
            "order_to_trade_ratio",
            "otr_breached",
            "max_drawdown",
            "regime_count",
            "losing_regimes",
            "worst_regime_equity_change",
            "spread_net",
            "markout_mean",
            "markout_win_rate",
        ]
    )
    checks = pd.DataFrame([{**check, "run": "preflight"}])
    summary = pd.DataFrame(
        [
            {
                "run_count": 0,
                "passed_runs": 0,
                "failed_runs": 1,
                "all_passed": False,
                "total_net_pnl": 0.0,
                "total_fills": 0,
                "worst_drawdown": 0.0,
                "worst_regime_equity_change": 0.0,
                "recommendation": "fix_quote_risk_review",
            }
        ]
    )
    metrics.to_csv(out / "proof_metrics.csv", index=False)
    checks.to_csv(out / "proof_checks.csv", index=False)
    summary.to_csv(out / "proof_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="proof_report",
        parameters={"preflight": "quote_risk_review"},
        inputs={},
    )
    return ProofReport(metrics=metrics, checks=checks, summary=summary, output_dir=out)


def _manifest_inputs(
    quotes_path: str | Path,
    chain_path: str | Path,
    quote_risk_review_dir: str | Path | None,
) -> dict[str, str | Path]:
    inputs: dict[str, str | Path] = {"quotes": quotes_path, "chain": chain_path}
    if quote_risk_review_dir is not None:
        inputs["quote_risk_review"] = Path(quote_risk_review_dir)
    return inputs


def _run_name(
    quote_ttl_ns: int,
    order_latency_us: float,
    fill_depth_fraction: float,
    markout_horizon_ns: int,
) -> str:
    return (
        f"ttl_{int(quote_ttl_ns)}ns"
        f"__order_{_label_number(order_latency_us)}us"
        f"__depth_{_label_number(fill_depth_fraction)}"
        f"__markout_{int(markout_horizon_ns)}ns"
    )


def _label_number(value: float) -> str:
    text = f"{float(value):g}"
    return text.replace("-", "m").replace(".", "p")


def _float_list(values: list[str]) -> list[float]:
    return [float(value) for value in values]


def _int_list(values: list[str]) -> list[int]:
    return [int(value) for value in values]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a surface market-making replay robustness sweep.")
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--quote-ttl-ns", nargs="+", required=True)
    parser.add_argument("--order-latency-us", nargs="+", default=["0"])
    parser.add_argument("--fill-depth-fraction", nargs="+", required=True)
    parser.add_argument("--markout-horizon-ns", nargs="+", default=["1000000000"])
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--option-tick", type=float, default=0.05)
    parser.add_argument("--contract-multiplier", type=float, default=1.0)
    parser.add_argument("--max-quotes", type=int, default=None)
    parser.add_argument("--min-net-pnl", type=float, default=0.0)
    parser.add_argument("--min-fills", type=int, default=1)
    parser.add_argument("--max-drawdown", type=float, default=None)
    parser.add_argument("--max-otr", type=float, default=None)
    parser.add_argument("--min-maker-share", type=float, default=1.0)
    parser.add_argument("--min-markout-mean", type=float, default=None)
    parser.add_argument("--quote-risk-review", default=None)
    parser.add_argument("--require-quote-risk-review", action="store_true")
    parser.add_argument("--fail-on-breach", action="store_true")
    args = parser.parse_args(argv)

    result = run_surface_mm_sweep(
        quotes_path=args.quotes,
        chain_path=args.chain,
        output_dir=args.out,
        quote_ttl_ns_values=_int_list(args.quote_ttl_ns),
        order_latency_us_values=_float_list(args.order_latency_us),
        fill_depth_fraction_values=_float_list(args.fill_depth_fraction),
        markout_horizon_ns_values=_int_list(args.markout_horizon_ns),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        option_tick=args.option_tick,
        contract_multiplier=args.contract_multiplier,
        max_quotes=args.max_quotes,
        quote_risk_review_dir=args.quote_risk_review,
        require_quote_risk_review=args.require_quote_risk_review,
        proof_thresholds=ProofThresholds(
            min_net_pnl=args.min_net_pnl,
            min_fills=args.min_fills,
            max_drawdown=args.max_drawdown,
            max_otr=args.max_otr,
            min_maker_share=args.min_maker_share,
            min_markout_mean=args.min_markout_mean,
        ),
    )
    print(result.summary.to_string(index=False))
    return 2 if (args.fail_on_breach or args.require_quote_risk_review) and not bool(result.proof.passed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
