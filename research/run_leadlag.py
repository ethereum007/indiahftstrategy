from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Optional

import numpy as np
import pandas as pd

from data.loaders import load_tick_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from research.leadlag import MEASUREMENT_RUN_TYPE, LeadLagSummary, summarize_pair


@dataclass(frozen=True)
class LeadLagRunResult:
    summary: LeadLagSummary
    output_dir: Optional[Path] = None


def run_leadlag(
    *,
    leader_path: str | Path,
    laggard_path: str | Path,
    output_dir: str | Path | None = None,
    leader_column_map: Optional[Mapping[str, str]] = None,
    laggard_column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    leader_tick_size: float = 0.05,
    laggard_tick_size: float = 0.05,
    lot_size: int = 75,
    delta: float = 1.0,
    innovation_ticks: float = 2.0,
    lags_ns: list[int] | None = None,
    latency_sweep_ns: list[int] | None = None,
    max_lag_ns: int = 50_000_000,
    depth_fraction: float = 0.25,
    correlation_tolerance_ns: int | None = None,
) -> LeadLagRunResult:
    leader_file = Path(leader_path).resolve()
    laggard_file = Path(laggard_path).resolve()
    leader_loaded = load_tick_csv(
        leader_file,
        column_map=leader_column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    )
    laggard_loaded = load_tick_csv(
        laggard_file,
        column_map=laggard_column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    )
    leader = leader_loaded.data
    laggard = laggard_loaded.data
    laggard_instrument = Instrument(
        "LAGGARD-OPT",
        Kind.OPT,
        lot_size=lot_size,
        tick=laggard_tick_size,
    )
    laggard_costs = IndianCostModel.nse_index_options()
    resolved_lags_ns = lags_ns or _default_lags_ns()
    resolved_latency_sweep_ns = latency_sweep_ns or _default_latency_sweep_ns()
    summary = summarize_pair(
        leader,
        laggard,
        leader_tick_size=leader_tick_size,
        laggard_tick_size=laggard_tick_size,
        laggard_instrument=laggard_instrument,
        laggard_costs=laggard_costs,
        delta=delta,
        innovation_ticks=innovation_ticks,
        lags_ns=resolved_lags_ns,
        latency_sweep_ns=resolved_latency_sweep_ns,
        max_lag_ns=max_lag_ns,
        depth_fraction=depth_fraction,
        correlation_tolerance_ns=correlation_tolerance_ns,
    )
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        summary.cross_correlation.to_csv(out_dir / "cross_correlation.csv", index=False)
        summary.lag_profile.to_csv(out_dir / "lag_profile.csv", index=False)
        summary.latency_curve.to_csv(out_dir / "latency_curve.csv", index=False)
        measure_summary = _measurement_summary(
            summary,
            leader_rows=len(leader),
            laggard_rows=len(laggard),
        )
        measure_summary.to_csv(out_dir / "leadlag_measure_summary.csv", index=False)
        config = {
            "run_type": MEASUREMENT_RUN_TYPE,
            "strategy": "lead_lag_taker",
            "market": INDIA_NSE_INDEX_DERIVATIVES.name,
            "leader_path": str(leader_file),
            "laggard_path": str(laggard_file),
            "loader": {
                "leader_column_map": dict(leader_column_map or {}),
                "laggard_column_map": dict(laggard_column_map or {}),
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": bool(filter_session),
                "leader_quarantine": asdict(leader_loaded.quarantine),
                "laggard_quarantine": asdict(laggard_loaded.quarantine),
            },
            "instrument": {
                "symbol": laggard_instrument.symbol,
                "kind": laggard_instrument.kind.value,
                "lot_size": laggard_instrument.lot_size,
                "tick": laggard_instrument.tick,
                "multiplier": laggard_instrument.multiplier,
            },
            "costs": asdict(laggard_costs),
            "measurement": {
                "leader_tick_size": leader_tick_size,
                "laggard_tick_size": laggard_tick_size,
                "delta": delta,
                "innovation_ticks": innovation_ticks,
                "lags_ns": list(resolved_lags_ns),
                "latency_sweep_ns": list(resolved_latency_sweep_ns),
                "max_lag_ns": max_lag_ns,
                "depth_fraction": depth_fraction,
                "correlation_tolerance_ns": correlation_tolerance_ns,
            },
            "authorizes_submission": False,
            "next_gate": "audit-leadlag-edge",
        }
        (out_dir / "leadlag_measure_config.json").write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (out_dir / "leadlag_measure_runbook.md").write_text(
            _measurement_runbook(measure_summary.iloc[0], out_dir),
            encoding="utf-8",
        )
        write_experiment_manifest(
            out_dir,
            run_type=MEASUREMENT_RUN_TYPE,
            parameters={
                "strategy": config["strategy"],
                "market": config["market"],
                "loader": config["loader"],
                "instrument": config["instrument"],
                "costs": config["costs"],
                "measurement": config["measurement"],
            },
            inputs={"leader": leader_file, "laggard": laggard_file},
            extra={
                "completed": True,
                "authorizes_submission": False,
                "next_gate": "audit-leadlag-edge",
            },
        )
    return LeadLagRunResult(summary=summary, output_dir=out_dir)


def _measurement_summary(
    summary: LeadLagSummary,
    *,
    leader_rows: int,
    laggard_rows: int,
) -> pd.DataFrame:
    correlation = summary.cross_correlation.copy()
    correlation["abs_correlation"] = pd.to_numeric(
        correlation.get("correlation"), errors="coerce"
    ).abs()
    best_correlation = (
        correlation.sort_values("abs_correlation", ascending=False).iloc[0]
        if correlation["abs_correlation"].notna().any()
        else None
    )
    latency = summary.latency_curve.copy()
    latency["net_pnl"] = pd.to_numeric(latency.get("net_pnl"), errors="coerce")
    best_latency = (
        latency.sort_values("net_pnl", ascending=False).iloc[0]
        if latency["net_pnl"].notna().any()
        else None
    )
    profitable = latency.loc[latency["net_pnl"] > 0]
    return pd.DataFrame(
        [
            {
                "completed": True,
                "strategy": "lead_lag_taker",
                "market": INDIA_NSE_INDEX_DERIVATIVES.name,
                "authorizes_submission": False,
                "leader_rows": int(leader_rows),
                "laggard_rows": int(laggard_rows),
                "correlation_rows": int(len(correlation)),
                "event_count": int(len(summary.lag_profile)),
                "latency_rows": int(len(latency)),
                "best_lag_ns": (
                    int(best_correlation["lag_ns"])
                    if best_correlation is not None
                    else np.nan
                ),
                "best_abs_correlation": (
                    float(best_correlation["abs_correlation"])
                    if best_correlation is not None
                    else np.nan
                ),
                "best_latency_ns": (
                    int(best_latency["latency_ns"])
                    if best_latency is not None
                    else np.nan
                ),
                "best_latency_net_pnl": (
                    float(best_latency["net_pnl"])
                    if best_latency is not None
                    else np.nan
                ),
                "max_positive_latency_ns": (
                    int(profitable["latency_ns"].max())
                    if not profitable.empty
                    else np.nan
                ),
                "next_gate": "audit-leadlag-edge",
            }
        ]
    )


def _measurement_runbook(row: pd.Series, output_dir: Path) -> str:
    return "\n".join(
        [
            "# Lead-Lag Measurement Runbook",
            "",
            "## Result",
            "",
            f"- Leader rows: {int(row['leader_rows'])}",
            f"- Laggard rows: {int(row['laggard_rows'])}",
            f"- Measured leader events: {int(row['event_count'])}",
            f"- Latency points: {int(row['latency_rows'])}",
            "- Order submission authorized: no",
            "",
            "## Provenance",
            "",
            "The manifest fingerprints both raw source files and every measurement artifact.",
            "Any source or artifact drift must be resolved by rerunning this measurement.",
            "",
            "## Next Gate",
            "",
            "```powershell",
            "python -m hft_cli audit-leadlag-edge `",
            f"  --measure \"{output_dir}\" `",
            f"  --out \"{output_dir.parent / (output_dir.name + '_edge')}\" `",
            "  --fail-on-breach",
            "```",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run lead-lag measurement for one leader/laggard pair.")
    parser.add_argument("--leader", required=True, help="Leader top-of-book CSV path.")
    parser.add_argument("--laggard", required=True, help="Laggard top-of-book CSV path.")
    parser.add_argument("--out", required=True, help="Output directory for CSV reports.")
    parser.add_argument("--leader-column-map", help="JSON mapping of normalized columns to source columns.")
    parser.add_argument("--laggard-column-map", help="JSON mapping of normalized columns to source columns.")
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--leader-tick-size", type=float, default=0.05)
    parser.add_argument("--laggard-tick-size", type=float, default=0.05)
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--delta", type=float, default=1.0)
    parser.add_argument("--innovation-ticks", type=float, default=2.0)
    parser.add_argument("--lags-ns", default=None, help="Comma-separated lag grid in ns.")
    parser.add_argument("--latency-sweep-ns", default=None, help="Comma-separated latency sweep in ns.")
    parser.add_argument("--max-lag-ns", type=int, default=50_000_000)
    parser.add_argument("--depth-fraction", type=float, default=0.25)
    parser.add_argument("--correlation-tolerance-ns", type=int, default=None)
    args = parser.parse_args(argv)

    result = run_leadlag(
        leader_path=args.leader,
        laggard_path=args.laggard,
        output_dir=args.out,
        leader_column_map=_json_map(args.leader_column_map),
        laggard_column_map=_json_map(args.laggard_column_map),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        leader_tick_size=args.leader_tick_size,
        laggard_tick_size=args.laggard_tick_size,
        lot_size=args.lot_size,
        delta=args.delta,
        innovation_ticks=args.innovation_ticks,
        lags_ns=_int_list(args.lags_ns) if args.lags_ns else None,
        latency_sweep_ns=_int_list(args.latency_sweep_ns) if args.latency_sweep_ns else None,
        max_lag_ns=args.max_lag_ns,
        depth_fraction=args.depth_fraction,
        correlation_tolerance_ns=args.correlation_tolerance_ns,
    )
    print(result.summary.latency_curve.to_string(index=False))
    return 0


def _json_map(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("column map must be a JSON object")
    return {str(key): str(val) for key, val in parsed.items()}


def _int_list(value: str) -> list[int]:
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def _default_lags_ns() -> list[int]:
    return [0, 50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000, 5_000_000, 10_000_000, 50_000_000]


def _default_latency_sweep_ns() -> list[int]:
    return [50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000]


if __name__ == "__main__":
    raise SystemExit(main())
