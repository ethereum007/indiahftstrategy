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
from strategies.microprice_imbalance import MicropriceImbalanceConfig, MicropriceImbalanceStrategy


@dataclass(frozen=True)
class ImbalanceReplayResult:
    result: MultiBacktestResult
    signals: pd.DataFrame
    summary: pd.DataFrame
    markouts: pd.DataFrame
    input_quarantine: pd.DataFrame
    output_dir: Path | None = None


def run_imbalance_replay(
    *,
    ticks_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
    instrument_id: str = "BOOK",
    instrument_kind: str = "OPT",
    lot_size: int = 75,
    tick_size: float = 0.05,
    qty: int = 75,
    entry_imbalance: float = 0.6,
    exit_imbalance: float = 0.15,
    min_microprice_edge_ticks: float = 0.25,
    max_spread_ticks: float = 2.0,
    min_depth: int = 1,
    hold_ns: int = 500_000_000,
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
) -> ImbalanceReplayResult:
    normalized_ticks = load_tick_csv(
        ticks_path,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
        market=market,
    )
    ticks = normalized_ticks.data
    input_quarantine = input_quarantine_frame(
        {"ticks": normalized_ticks.quarantine},
        dataset_types={"ticks": "l1_ticks"},
    )
    kind = _kind(instrument_kind)
    venue = _venue(market)
    strategy = MicropriceImbalanceStrategy(
        MicropriceImbalanceConfig(
            instrument_id=instrument_id,
            qty=qty,
            tick_size=tick_size,
            entry_imbalance=entry_imbalance,
            exit_imbalance=exit_imbalance,
            min_microprice_edge_ticks=min_microprice_edge_ticks,
            max_spread_ticks=max_spread_ticks,
            min_depth=min_depth,
            hold_ns=hold_ns,
            cooloff_ns=cooloff_ns,
        )
    )
    engine = MultiInstrumentEngine(
        instruments={
            instrument_id: InstrumentConfig(
                Instrument(instrument_id, kind, lot_size=lot_size, tick=tick_size),
                venue,
                ticks,
                costs=_costs(
                    kind,
                    market=market,
                    generic_buy_notional_rate=generic_buy_notional_rate,
                    generic_sell_notional_rate=generic_sell_notional_rate,
                    generic_per_unit_fee=generic_per_unit_fee,
                    generic_per_contract_fee=generic_per_contract_fee,
                    generic_per_order_fee=generic_per_order_fee,
                ),
                max_position_lots=max_position_lots,
            )
        },
        venues={
            venue: VenueConfig(
                venue,
                LatencyModel(
                    feed_us=feed_latency_us,
                    order_us=order_latency_us,
                    jitter_us=0,
                    _rng=np.random.default_rng(31),
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
    signals = pd.DataFrame(strategy.signals)
    strategy_fills = result.fills.loc[result.fills["oid"].isin(strategy_orders)] if not result.fills.empty else result.fills
    markouts = (
        compute_markouts(
            strategy_fills,
            ticks,
            horizons_ns=markout_horizons_ns or [100_000_000, 1_000_000_000],
        )
        if not strategy_fills.empty
        else pd.DataFrame()
    )

    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        write_replay_outputs(
            result=result,
            output_dir=out_dir,
            summary=summary,
            strategy_order_ids=strategy_orders,
            extra_frames={
                "signals": signals,
                "markouts": markouts,
                "input_quarantine": input_quarantine,
            },
            manifest_run_type="imbalance_replay",
            manifest_inputs={"ticks": ticks_path},
            manifest_parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "market": market,
                "instrument_id": instrument_id,
                "instrument_kind": kind.value,
                "lot_size": lot_size,
                "tick_size": tick_size,
                "qty": qty,
                "entry_imbalance": entry_imbalance,
                "exit_imbalance": exit_imbalance,
                "min_microprice_edge_ticks": min_microprice_edge_ticks,
                "max_spread_ticks": max_spread_ticks,
                "min_depth": min_depth,
                "hold_ns": hold_ns,
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
    return ImbalanceReplayResult(
        result=result,
        signals=signals,
        summary=summary,
        markouts=markouts,
        input_quarantine=input_quarantine,
        output_dir=out_dir,
    )


def _kind(value: str) -> Kind:
    normalized = value.strip().upper()
    try:
        return Kind(normalized)
    except ValueError as exc:
        raise ValueError("instrument_kind must be one of FUT, OPT, or EQ") from exc


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
    parser = argparse.ArgumentParser(description="Replay microprice/order-book imbalance strategy.")
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
    parser.add_argument("--entry-imbalance", type=float, default=0.6)
    parser.add_argument("--exit-imbalance", type=float, default=0.15)
    parser.add_argument("--min-microprice-edge-ticks", type=float, default=0.25)
    parser.add_argument("--max-spread-ticks", type=float, default=2.0)
    parser.add_argument("--min-depth", type=int, default=1)
    parser.add_argument("--hold-ns", type=int, default=500_000_000)
    parser.add_argument("--cooloff-ns", type=int, default=0)
    parser.add_argument("--feed-latency-us", type=float, default=0.0)
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    parser.add_argument("--generic-buy-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-sell-notional-rate", type=float, default=0.0)
    parser.add_argument("--generic-per-unit-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-contract-fee", type=float, default=0.0)
    parser.add_argument("--generic-per-order-fee", type=float, default=0.0)
    args = parser.parse_args(argv)
    replay = run_imbalance_replay(
        ticks_path=args.ticks,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        market=args.market,
        instrument_id=args.instrument_id,
        instrument_kind=args.instrument_kind,
        lot_size=args.lot_size,
        tick_size=args.tick_size,
        qty=args.qty,
        entry_imbalance=args.entry_imbalance,
        exit_imbalance=args.exit_imbalance,
        min_microprice_edge_ticks=args.min_microprice_edge_ticks,
        max_spread_ticks=args.max_spread_ticks,
        min_depth=args.min_depth,
        hold_ns=args.hold_ns,
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
