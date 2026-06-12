from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.loaders import load_tick_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiBacktestResult, MultiInstrumentEngine, VenueConfig
from reports.replay import replay_summary, write_replay_outputs
from research.markouts import compute_markouts
from strategies.leadlag_taker import LeadLagTakerConfig, LeadLagTakerStrategy


@dataclass(frozen=True)
class LeadLagReplayResult:
    result: MultiBacktestResult
    summary: pd.DataFrame
    markouts: pd.DataFrame
    output_dir: Path | None = None


def run_leadlag_replay(
    *,
    leader_path: str | Path,
    laggard_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    lot_size: int = 75,
    leader_tick: float = 0.05,
    laggard_tick: float = 0.05,
    delta: float = 1.0,
    trigger_ticks: float = 3.0,
    qty: int = 75,
    flat_after_ns: int = 500_000_000,
    cooloff_ns: int = 0,
    feed_latency_us: float = 0.0,
    order_latency_us: float = 0.0,
    max_position_lots: int = 20,
    markout_horizons_ns: list[int] | None = None,
) -> LeadLagReplayResult:
    leader = load_tick_csv(
        leader_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    ).data
    laggard = load_tick_csv(
        laggard_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    ).data
    strategy = LeadLagTakerStrategy(
        LeadLagTakerConfig(
            leader_id="LEADER",
            laggard_id="LAGGARD",
            qty=qty,
            delta=delta,
            leader_tick=leader_tick,
            laggard_tick=laggard_tick,
            trigger_ticks=trigger_ticks,
            flat_after_ns=flat_after_ns,
            cooloff_ns=cooloff_ns,
        )
    )
    engine = MultiInstrumentEngine(
        instruments={
            "LEADER": InstrumentConfig(
                Instrument("LEADER", Kind.FUT, lot_size=lot_size, tick=leader_tick),
                "NSE",
                leader,
                costs=IndianCostModel.nse_index_futures(),
                max_position_lots=max_position_lots,
            ),
            "LAGGARD": InstrumentConfig(
                Instrument("LAGGARD", Kind.OPT, lot_size=lot_size, tick=laggard_tick),
                "NSE",
                laggard,
                costs=IndianCostModel.nse_index_options(),
                max_position_lots=max_position_lots,
                delta_per_unit=delta,
            ),
        },
        venues={
            "NSE": VenueConfig(
                "NSE",
                LatencyModel(
                    feed_us=feed_latency_us,
                    order_us=order_latency_us,
                    jitter_us=0,
                    _rng=np.random.default_rng(23),
                ),
            )
        },
        strategy=strategy,
    )
    result = engine.run()
    strategy_orders = strategy.entry_orders + strategy.exit_orders
    summary = replay_summary(result, strategy_orders=strategy_orders)
    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy_orders)] if not result.fills.empty else result.fills
    markouts = compute_markouts(
        strategy_fills,
        laggard,
        horizons_ns=markout_horizons_ns or [100_000_000, 1_000_000_000],
    ) if not strategy_fills.empty else pd.DataFrame()
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        write_replay_outputs(
            result=result,
            output_dir=out_dir,
            summary=summary,
            strategy_order_ids=strategy_orders,
            extra_frames={"markouts": markouts},
            manifest_run_type="leadlag_replay",
            manifest_inputs={"leader": leader_path, "laggard": laggard_path},
            manifest_parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "lot_size": lot_size,
                "leader_tick": leader_tick,
                "laggard_tick": laggard_tick,
                "delta": delta,
                "trigger_ticks": trigger_ticks,
                "qty": qty,
                "flat_after_ns": flat_after_ns,
                "cooloff_ns": cooloff_ns,
                "feed_latency_us": feed_latency_us,
                "order_latency_us": order_latency_us,
                "max_position_lots": max_position_lots,
                "markout_horizons_ns": markout_horizons_ns or [100_000_000, 1_000_000_000],
            },
        )
    return LeadLagReplayResult(result, summary, markouts, out_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay lead-lag stale-quote taker strategy.")
    parser.add_argument("--leader", required=True)
    parser.add_argument("--laggard", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--leader-tick", type=float, default=0.05)
    parser.add_argument("--laggard-tick", type=float, default=0.05)
    parser.add_argument("--delta", type=float, default=1.0)
    parser.add_argument("--trigger-ticks", type=float, default=3.0)
    parser.add_argument("--qty", type=int, default=75)
    parser.add_argument("--flat-after-ns", type=int, default=500_000_000)
    parser.add_argument("--cooloff-ns", type=int, default=0)
    parser.add_argument("--feed-latency-us", type=float, default=0.0)
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    args = parser.parse_args(argv)
    replay = run_leadlag_replay(
        leader_path=args.leader,
        laggard_path=args.laggard,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        lot_size=args.lot_size,
        leader_tick=args.leader_tick,
        laggard_tick=args.laggard_tick,
        delta=args.delta,
        trigger_ticks=args.trigger_ticks,
        qty=args.qty,
        flat_after_ns=args.flat_after_ns,
        cooloff_ns=args.cooloff_ns,
        feed_latency_us=args.feed_latency_us,
        order_latency_us=args.order_latency_us,
    )
    print(replay.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
