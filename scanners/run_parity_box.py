from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

import pandas as pd

from data.chains import load_option_chain_csv
from data.loaders import load_tick_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.manifest import write_experiment_manifest
from scanners.parity_box import (
    ScannerCosts,
    ScannerInstruments,
    opportunity_report,
    scan_boxes,
    scan_parity_with_audit,
)


PARITY_SCAN_RUN_TYPE = "parity_box_scan"
PARITY_SCAN_REQUIRED_ARTIFACTS = (
    "parity_opportunities.csv",
    "box_opportunities.csv",
    "opportunity_report.csv",
    "parity_futures_join_audit.csv",
)


@dataclass(frozen=True)
class ParityBoxRunResult:
    parity: pd.DataFrame
    boxes: pd.DataFrame
    report: pd.DataFrame
    futures_join_audit: pd.DataFrame
    output_dir: Optional[Path] = None


def run_scan(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path | None = None,
    chain_column_map: Optional[Mapping[str, str]] = None,
    futures_column_map: Optional[Mapping[str, str]] = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    lot_size: int = 75,
    option_tick: float = 0.05,
    future_tick: float = 0.05,
    asof_latency_ns: int = 0,
    tolerance_ns: Optional[int] = 1_000_000,
    depth_fraction: float = 0.25,
) -> ParityBoxRunResult:
    chain = load_option_chain_csv(
        chain_path,
        column_map=chain_column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    ).data
    futures = load_tick_csv(
        futures_path,
        column_map=futures_column_map,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    ).data
    option = Instrument("INDEX-OPT", Kind.OPT, lot_size=lot_size, tick=option_tick)
    future = Instrument("INDEX-FUT", Kind.FUT, lot_size=lot_size, tick=future_tick)
    instruments = ScannerInstruments(option=option, future=future)
    costs = ScannerCosts(
        option=IndianCostModel.nse_index_options(),
        future=IndianCostModel.nse_index_futures(),
    )

    parity_scan = scan_parity_with_audit(
        chain,
        futures,
        instruments=instruments,
        costs=costs,
        asof_latency_ns=asof_latency_ns,
        tolerance_ns=tolerance_ns,
        depth_fraction=depth_fraction,
    )
    parity = parity_scan.opportunities
    futures_join_audit = parity_scan.futures_join_audit
    boxes = scan_boxes(
        chain,
        option_instrument=option,
        option_costs=costs.option,
        depth_fraction=depth_fraction,
    )
    combined = pd.concat(
        [
            parity.assign(scanner="parity"),
            boxes.assign(scanner="box"),
        ],
        ignore_index=True,
        sort=False,
    )
    report = opportunity_report(combined)
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        parity.to_csv(out_dir / "parity_opportunities.csv", index=False)
        boxes.to_csv(out_dir / "box_opportunities.csv", index=False)
        report.to_csv(out_dir / "opportunity_report.csv", index=False)
        futures_join_audit.to_csv(
            out_dir / "parity_futures_join_audit.csv",
            index=False,
        )
        write_experiment_manifest(
            out_dir,
            run_type=PARITY_SCAN_RUN_TYPE,
            inputs={
                "chain": chain_path,
                "futures": futures_path,
            },
            parameters={
                "chain_column_map": chain_column_map,
                "futures_column_map": futures_column_map,
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "market": market,
                "lot_size": lot_size,
                "option_tick": option_tick,
                "future_tick": future_tick,
                "asof_latency_ns": asof_latency_ns,
                "max_futures_quote_age_ns": tolerance_ns,
                "depth_fraction": depth_fraction,
            },
        )
    return ParityBoxRunResult(
        parity=parity,
        boxes=boxes,
        report=report,
        futures_join_audit=futures_join_audit,
        output_dir=out_dir,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run executable parity/box opportunity scanner.")
    parser.add_argument("--chain", required=True, help="Option-chain CSV path.")
    parser.add_argument("--futures", required=True, help="Futures top-of-book CSV path.")
    parser.add_argument("--out", required=True, help="Output directory for CSV reports.")
    parser.add_argument("--chain-column-map", help="JSON mapping of normalized chain columns to source columns.")
    parser.add_argument("--futures-column-map", help="JSON mapping of normalized futures columns to source columns.")
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--market", default=INDIA_NSE_INDEX_DERIVATIVES.name)
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--asof-latency-ns", type=int, default=0)
    parser.add_argument(
        "--max-futures-quote-age-ns",
        "--tolerance-ns",
        dest="tolerance_ns",
        type=int,
        default=1_000_000,
    )
    parser.add_argument("--depth-fraction", type=float, default=0.25)
    args = parser.parse_args(argv)

    result = run_scan(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        chain_column_map=_json_map(args.chain_column_map),
        futures_column_map=_json_map(args.futures_column_map),
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        market=args.market,
        lot_size=args.lot_size,
        asof_latency_ns=args.asof_latency_ns,
        tolerance_ns=args.tolerance_ns,
        depth_fraction=args.depth_fraction,
    )
    print(result.report.to_string(index=False))
    return 0


def _json_map(value: str | None) -> dict[str, str] | None:
    if not value:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("column map must be a JSON object")
    return {str(key): str(val) for key, val in parsed.items()}


if __name__ == "__main__":
    raise SystemExit(main())
