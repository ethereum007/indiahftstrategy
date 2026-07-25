from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.loaders import load_tick_csv
from engine.costs import GenericCostModel
from engine.hft_backtest import IndianCostModel, Instrument, Kind, LatencyModel
from engine.multi_engine import InstrumentConfig, MultiBacktestResult, MultiInstrumentEngine, VenueConfig
from markets.profiles import INDIA_NSE_INDEX_DERIVATIVES
from reports.replay import (
    input_quarantine_frame,
    replay_summary,
    write_replay_outputs,
)
from research.markouts import compute_markouts
from strategies.leadlag_taker import LeadLagTakerConfig, LeadLagTakerStrategy


LEAD_LAG_STRATEGY = "lead_lag_taker"


@dataclass(frozen=True)
class LeadLagReplayResult:
    result: MultiBacktestResult
    summary: pd.DataFrame
    markouts: pd.DataFrame
    input_quarantine: pd.DataFrame
    output_dir: Path | None = None


def run_leadlag_replay(
    *,
    leader_path: str | Path,
    laggard_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
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
    generic_buy_notional_rate: float = 0.0,
    generic_sell_notional_rate: float = 0.0,
    generic_per_unit_fee: float = 0.0,
    generic_per_contract_fee: float = 0.0,
    generic_per_order_fee: float = 0.0,
    max_position_lots: int = 20,
    markout_horizons_ns: list[int] | None = None,
) -> LeadLagReplayResult:
    normalized_leader = load_tick_csv(
        leader_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    )
    normalized_laggard = load_tick_csv(
        laggard_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    )
    leader = normalized_leader.data
    laggard = normalized_laggard.data
    input_quarantine = input_quarantine_frame(
        {
            "leader": normalized_leader.quarantine,
            "laggard": normalized_laggard.quarantine,
        },
        dataset_types={
            "leader": "l1_ticks",
            "laggard": "l1_ticks",
        },
    )
    venue = _venue(market)
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
                venue,
                leader,
                costs=_costs(
                    Kind.FUT,
                    market=market,
                    generic_buy_notional_rate=generic_buy_notional_rate,
                    generic_sell_notional_rate=generic_sell_notional_rate,
                    generic_per_unit_fee=generic_per_unit_fee,
                    generic_per_contract_fee=generic_per_contract_fee,
                    generic_per_order_fee=generic_per_order_fee,
                ),
                max_position_lots=max_position_lots,
            ),
            "LAGGARD": InstrumentConfig(
                Instrument("LAGGARD", Kind.OPT, lot_size=lot_size, tick=laggard_tick),
                venue,
                laggard,
                costs=_costs(
                    Kind.OPT,
                    market=market,
                    generic_buy_notional_rate=generic_buy_notional_rate,
                    generic_sell_notional_rate=generic_sell_notional_rate,
                    generic_per_unit_fee=generic_per_unit_fee,
                    generic_per_contract_fee=generic_per_contract_fee,
                    generic_per_order_fee=generic_per_order_fee,
                ),
                max_position_lots=max_position_lots,
                delta_per_unit=delta,
            ),
        },
        venues={
            venue: VenueConfig(
                venue,
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
    summary = replay_summary(
        result,
        strategy_orders=strategy_orders,
        input_quarantine=input_quarantine,
    )
    summary["strategy"] = LEAD_LAG_STRATEGY
    summary["market"] = market
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
            extra_frames={
                "markouts": markouts,
                "input_quarantine": input_quarantine,
            },
            manifest_run_type="leadlag_replay",
            manifest_inputs={"leader": leader_path, "laggard": laggard_path},
            manifest_parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "strategy": LEAD_LAG_STRATEGY,
                "market": market,
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
                "generic_costs": {
                    "buy_notional_rate": generic_buy_notional_rate,
                    "sell_notional_rate": generic_sell_notional_rate,
                    "per_unit_fee": generic_per_unit_fee,
                    "per_contract_fee": generic_per_contract_fee,
                    "per_order_fee": generic_per_order_fee,
                },
                "max_position_lots": max_position_lots,
                "markout_horizons_ns": markout_horizons_ns or [100_000_000, 1_000_000_000],
            },
        )
    return LeadLagReplayResult(
        result=result,
        summary=summary,
        markouts=markouts,
        input_quarantine=input_quarantine,
        output_dir=out_dir,
    )


def _costs(
    kind: Kind,
    *,
    market: str,
    generic_buy_notional_rate: float,
    generic_sell_notional_rate: float,
    generic_per_unit_fee: float,
    generic_per_contract_fee: float,
    generic_per_order_fee: float,
):
    if market != INDIA_NSE_INDEX_DERIVATIVES.name:
        return GenericCostModel(
            buy_notional_rate=generic_buy_notional_rate,
            sell_notional_rate=generic_sell_notional_rate,
            per_unit_fee=generic_per_unit_fee,
            per_contract_fee=generic_per_contract_fee,
            per_order_fee=generic_per_order_fee,
        )
    if kind == Kind.FUT:
        return IndianCostModel.nse_index_futures()
    return IndianCostModel.nse_index_options()


def _venue(market: str) -> str:
    return "NSE" if market == INDIA_NSE_INDEX_DERIVATIVES.name else market.upper()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay lead-lag stale-quote taker strategy.")
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
    parser.add_argument("--trigger-ticks", type=float, default=3.0)
    parser.add_argument("--qty", type=int, default=75)
    parser.add_argument("--flat-after-ns", type=int, default=500_000_000)
    parser.add_argument("--cooloff-ns", type=int, default=0)
    parser.add_argument("--feed-latency-us", type=float, default=0.0)
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    parser.add_argument("--generic-buy-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-sell-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-per-unit-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-contract-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-order-fee", type=float, default=0.0)
    args = parser.parse_args(argv)
    replay = run_leadlag_replay(
        leader_path=args.leader,
        laggard_path=args.laggard,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        market=args.market,
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
        generic_buy_notional_rate=args.generic_buy_notional_rate,
        generic_sell_notional_rate=args.generic_sell_notional_rate,
        generic_per_unit_fee=args.generic_per_unit_fee,
        generic_per_contract_fee=args.generic_per_contract_fee,
        generic_per_order_fee=args.generic_per_order_fee,
    )
    print(replay.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
