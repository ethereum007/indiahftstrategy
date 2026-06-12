from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv, normalize_option_chain
from data.loaders import load_tick_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiBacktestResult, MultiInstrumentEngine, VenueConfig
from reports.replay import replay_summary, write_replay_outputs
from scanners.parity_box import ScannerCosts, ScannerInstruments, scan_parity
from strategies.parity_arb import ParityArbConfig, ParityArbTakerStrategy, ParityLegMap


@dataclass(frozen=True)
class ParityReplayResult:
    result: MultiBacktestResult
    signals: pd.DataFrame
    summary: pd.DataFrame
    legging: pd.DataFrame
    output_dir: Path | None = None


def run_parity_replay(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    option_tick: float = 0.05,
    future_tick: float = 0.05,
    asof_latency_ns: int = 0,
    depth_fraction: float = 0.25,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    max_signal_age_ns: int = 1_000_000,
    max_qty: int | None = None,
    max_position_lots: int = 20,
    signal_limit: int | None = None,
) -> ParityReplayResult:
    chain = load_option_chain_csv(
        chain_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    ).data
    futures = load_tick_csv(
        futures_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    ).data

    option = Instrument("INDEX-OPT", Kind.OPT, lot_size=lot_size, tick=option_tick)
    future = Instrument("INDEX-FUT", Kind.FUT, lot_size=lot_size, tick=future_tick)
    option_costs = IndianCostModel.nse_index_options()
    future_costs = IndianCostModel.nse_index_futures()
    signals = scan_parity(
        chain,
        futures,
        instruments=ScannerInstruments(option=option, future=future),
        costs=ScannerCosts(option=option_costs, future=future_costs),
        asof_latency_ns=asof_latency_ns,
        depth_fraction=depth_fraction,
    )
    if signal_limit is not None:
        signals = signals.head(signal_limit).copy()

    instruments, leg_map = _build_instruments(
        chain=chain,
        futures=futures,
        lot_size=lot_size,
        option_tick=option_tick,
        future_tick=future_tick,
        option_costs=option_costs,
        future_costs=future_costs,
        max_position_lots=max_position_lots,
    )
    strategy = ParityArbTakerStrategy(
        signals,
        leg_map,
        ParityArbConfig(max_signal_age_ns=max_signal_age_ns, max_qty=max_qty),
    )
    engine = MultiInstrumentEngine(
        instruments=instruments,
        venues={
            "NSE": VenueConfig(
                "NSE",
                LatencyModel(
                    feed_us=feed_latency_us,
                    order_us=order_latency_us,
                    jitter_us=0,
                    _rng=np.random.default_rng(17),
                ),
            )
        },
        strategy=strategy,
    )
    result = engine.run()
    strategy_order_ids = [oid for execution in strategy.executions for oid in execution.order_ids]
    summary = replay_summary(result, strategy_orders=strategy_order_ids)
    legging = strategy.legging_report()
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        write_replay_outputs(
            result=result,
            output_dir=out_dir,
            summary=summary,
            strategy_order_ids=strategy_order_ids,
            extra_frames={"signals": signals, "legging": legging},
        )
    return ParityReplayResult(result, signals, summary, legging, out_dir)


def _build_instruments(
    *,
    chain: pd.DataFrame,
    futures: pd.DataFrame,
    lot_size: int,
    option_tick: float,
    future_tick: float,
    option_costs: IndianCostModel,
    future_costs: IndianCostModel,
    max_position_lots: int,
) -> tuple[dict[str, InstrumentConfig], ParityLegMap]:
    instruments: dict[str, InstrumentConfig] = {}
    call_by_strike: dict[float, str] = {}
    put_by_strike: dict[float, str] = {}
    for strike, group in chain.groupby("strike", sort=True):
        strike_float = float(strike)
        strike_label = _strike_label(strike_float)
        call_id = f"CALL_{strike_label}"
        put_id = f"PUT_{strike_label}"
        call_by_strike[strike_float] = call_id
        put_by_strike[strike_float] = put_id
        instruments[call_id] = InstrumentConfig(
            Instrument(call_id, Kind.OPT, lot_size=lot_size, tick=option_tick),
            "NSE",
            _option_side_book(group, "call"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
        instruments[put_id] = InstrumentConfig(
            Instrument(put_id, Kind.OPT, lot_size=lot_size, tick=option_tick),
            "NSE",
            _option_side_book(group, "put"),
            costs=option_costs,
            max_position_lots=max_position_lots,
        )
    instruments["FUT"] = InstrumentConfig(
        Instrument("FUT", Kind.FUT, lot_size=lot_size, tick=future_tick),
        "NSE",
        futures,
        costs=future_costs,
        max_position_lots=max_position_lots,
    )
    return instruments, ParityLegMap("FUT", call_by_strike, put_by_strike)


def _option_side_book(group: pd.DataFrame, side: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": group["ts"].to_numpy(),
            "bid": group[f"{side}_bid"].to_numpy(),
            "ask": group[f"{side}_ask"].to_numpy(),
            "bid_qty": group[f"{side}_bid_qty"].to_numpy(),
            "ask_qty": group[f"{side}_ask_qty"].to_numpy(),
            "last": np.nan,
            "last_qty": 0,
        }
    )


def _strike_label(strike: float) -> str:
    return str(strike).replace(".", "_")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay executable parity scanner signals.")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--futures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--asof-latency-ns", type=int, default=0)
    parser.add_argument("--depth-fraction", type=float, default=0.25)
    parser.add_argument("--feed-latency-us", type=float, default=0.0)
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    parser.add_argument("--max-signal-age-ns", type=int, default=1_000_000)
    parser.add_argument("--max-qty", type=int, default=None)
    parser.add_argument("--signal-limit", type=int, default=None)
    args = parser.parse_args(argv)
    replay = run_parity_replay(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        asof_latency_ns=args.asof_latency_ns,
        depth_fraction=args.depth_fraction,
        feed_latency_us=args.feed_latency_us,
        order_latency_us=args.order_latency_us,
        max_signal_age_ns=args.max_signal_age_ns,
        max_qty=args.max_qty,
        signal_limit=args.signal_limit,
    )
    print(replay.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
