from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv
from data.loaders import load_tick_csv
from engine.surface import fit_quadratic_smile
from reports.manifest import write_experiment_manifest
from strategies.surface_mm import QuoteBudget, SurfaceQuoteConfig, generate_surface_quotes


@dataclass(frozen=True)
class SurfaceQuoteRunResult:
    quotes: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None


def run_surface_quote_generation(
    *,
    chain_path: str | Path,
    futures_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    asof_latency_ns: int = 0,
    tte_years: float = 30 / 365,
    tick_size: float = 0.05,
    lot_size: int = 75,
    quote_lots: int = 1,
    edge_ticks: float = 2.0,
    inventory_skew_ticks_per_lot: float = 0.5,
    max_market_spread_ticks: float | None = None,
    max_quotes_per_snapshot: int | None = None,
    max_snapshots: int | None = None,
) -> SurfaceQuoteRunResult:
    if asof_latency_ns < 0:
        raise ValueError("asof_latency_ns must be non-negative")
    if tte_years <= 0:
        raise ValueError("tte_years must be positive")

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
    quotes = generate_surface_quotes_from_data(
        chain,
        futures,
        asof_latency_ns=asof_latency_ns,
        tte_years=tte_years,
        config=SurfaceQuoteConfig(
            tick_size=tick_size,
            lot_size=lot_size,
            quote_lots=quote_lots,
            edge_ticks=edge_ticks,
            inventory_skew_ticks_per_lot=inventory_skew_ticks_per_lot,
            max_market_spread_ticks=max_market_spread_ticks,
            max_quotes=max_quotes_per_snapshot,
        ),
        max_snapshots=max_snapshots,
    )
    summary = surface_quote_summary(quotes)
    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        quotes.to_csv(out_dir / "surface_quotes.csv", index=False)
        summary.to_csv(out_dir / "surface_quote_summary.csv", index=False)
        write_experiment_manifest(
            out_dir,
            run_type="surface_quote_generation",
            inputs={"chain": chain_path, "futures": futures_path},
            parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "asof_latency_ns": asof_latency_ns,
                "tte_years": tte_years,
                "tick_size": tick_size,
                "lot_size": lot_size,
                "quote_lots": quote_lots,
                "edge_ticks": edge_ticks,
                "inventory_skew_ticks_per_lot": inventory_skew_ticks_per_lot,
                "max_market_spread_ticks": max_market_spread_ticks,
                "max_quotes_per_snapshot": max_quotes_per_snapshot,
                "max_snapshots": max_snapshots,
            },
        )
    return SurfaceQuoteRunResult(quotes=quotes, summary=summary, output_dir=out_dir)


def generate_surface_quotes_from_data(
    chain: pd.DataFrame,
    futures: pd.DataFrame,
    *,
    asof_latency_ns: int,
    tte_years: float,
    config: SurfaceQuoteConfig,
    max_snapshots: int | None = None,
) -> pd.DataFrame:
    if chain.empty:
        return _empty_quotes()
    futures_ref = futures.sort_values("ts").copy()
    futures_ref["forward"] = 0.5 * (futures_ref["bid"] + futures_ref["ask"])
    snapshot_keys = list(chain.sort_values(["ts", "expiry"]).groupby(["ts", "expiry"], sort=True).groups)
    if max_snapshots is not None:
        snapshot_keys = snapshot_keys[:max_snapshots]

    rows = []
    for ts, expiry in snapshot_keys:
        snapshot = chain.loc[(chain["ts"] == ts) & (chain["expiry"] == expiry)].copy()
        lookup_ts = int(ts) - asof_latency_ns
        future = futures_ref.loc[futures_ref["ts"] <= lookup_ts].tail(1)
        if future.empty:
            continue
        forward = float(future.iloc[0]["forward"])
        surface_inputs = _surface_inputs(snapshot)
        try:
            surface = fit_quadratic_smile(surface_inputs, forward=forward, tte_years=tte_years)
        except ValueError:
            continue
        universe = _quote_universe(snapshot, tick_size=config.tick_size)
        generated = generate_surface_quotes(
            universe,
            surface,
            config=config,
            budget=QuoteBudget(max_order_messages=config.max_quotes) if config.max_quotes is not None else None,
        )
        if generated.empty:
            continue
        enriched = generated.merge(
            universe[["instrument_id", "market_bid", "market_ask", "market_spread_ticks"]],
            on="instrument_id",
            how="left",
        )
        enriched["ts"] = int(ts)
        enriched["expiry"] = expiry
        enriched["forward"] = forward
        enriched["futures_ts"] = int(future.iloc[0]["ts"])
        enriched["marketable"] = (
            ((enriched["side"] > 0) & (enriched["price"] >= enriched["market_ask"]))
            | ((enriched["side"] < 0) & (enriched["price"] <= enriched["market_bid"]))
        )
        enriched["quote_edge"] = np.where(
            enriched["side"] > 0,
            enriched["theo"] - enriched["price"],
            enriched["price"] - enriched["theo"],
        )
        rows.append(enriched)
    if not rows:
        return _empty_quotes()
    return pd.concat(rows, ignore_index=True, sort=False).sort_values(
        ["ts", "instrument_id", "side"],
    ).reset_index(drop=True)


def surface_quote_summary(quotes: pd.DataFrame) -> pd.DataFrame:
    if quotes.empty:
        return pd.DataFrame(
            columns=[
                "snapshots",
                "quotes",
                "instruments",
                "marketable_quotes",
                "avg_quote_edge",
                "min_quote_edge",
                "avg_market_spread_ticks",
            ]
        )
    return pd.DataFrame(
        [
            {
                "snapshots": int(quotes[["ts", "expiry"]].drop_duplicates().shape[0]),
                "quotes": int(len(quotes)),
                "instruments": int(quotes["instrument_id"].nunique()),
                "marketable_quotes": int(quotes["marketable"].sum()),
                "avg_quote_edge": float(quotes["quote_edge"].mean()),
                "min_quote_edge": float(quotes["quote_edge"].min()),
                "avg_market_spread_ticks": float(quotes["market_spread_ticks"].mean(skipna=True)),
            }
        ]
    )


def _surface_inputs(snapshot: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in snapshot.itertuples(index=False):
        rows.extend(
            [
                {
                    "strike": float(row.strike),
                    "option_type": "C",
                    "mid": 0.5 * (float(row.call_bid) + float(row.call_ask)),
                },
                {
                    "strike": float(row.strike),
                    "option_type": "P",
                    "mid": 0.5 * (float(row.put_bid) + float(row.put_ask)),
                },
            ]
        )
    return pd.DataFrame(rows)


def _quote_universe(snapshot: pd.DataFrame, *, tick_size: float) -> pd.DataFrame:
    rows = []
    for row in snapshot.itertuples(index=False):
        strike_label = str(float(row.strike)).replace(".", "_")
        rows.extend(
            [
                {
                    "instrument_id": f"CALL_{strike_label}",
                    "strike": float(row.strike),
                    "option_type": "C",
                    "bid": float(row.call_bid),
                    "ask": float(row.call_ask),
                    "market_bid": float(row.call_bid),
                    "market_ask": float(row.call_ask),
                },
                {
                    "instrument_id": f"PUT_{strike_label}",
                    "strike": float(row.strike),
                    "option_type": "P",
                    "bid": float(row.put_bid),
                    "ask": float(row.put_ask),
                    "market_bid": float(row.put_bid),
                    "market_ask": float(row.put_ask),
                },
            ]
        )
    out = pd.DataFrame(rows)
    out["market_spread_ticks"] = (out["ask"] - out["bid"]) / tick_size
    return out


def _empty_quotes() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ts",
            "expiry",
            "instrument_id",
            "strike",
            "option_type",
            "side",
            "price",
            "qty",
            "theo",
            "implied_vol",
            "edge_ticks",
            "inventory_lots",
            "skew_ticks",
            "market_bid",
            "market_ask",
            "market_spread_ticks",
            "forward",
            "futures_ts",
            "marketable",
            "quote_edge",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate surface-driven market-making quotes.")
    parser.add_argument("--chain", required=True)
    parser.add_argument("--futures", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--asof-latency-ns", type=int, default=0)
    parser.add_argument("--tte-years", type=float, default=30 / 365)
    parser.add_argument("--tick-size", type=float, default=0.05)
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--quote-lots", type=int, default=1)
    parser.add_argument("--edge-ticks", type=float, default=2.0)
    parser.add_argument("--inventory-skew-ticks-per-lot", type=float, default=0.5)
    parser.add_argument("--max-market-spread-ticks", type=float, default=None)
    parser.add_argument("--max-quotes-per-snapshot", type=int, default=None)
    parser.add_argument("--max-snapshots", type=int, default=None)
    args = parser.parse_args(argv)
    result = run_surface_quote_generation(
        chain_path=args.chain,
        futures_path=args.futures,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        asof_latency_ns=args.asof_latency_ns,
        tte_years=args.tte_years,
        tick_size=args.tick_size,
        lot_size=args.lot_size,
        quote_lots=args.quote_lots,
        edge_ticks=args.edge_ticks,
        inventory_skew_ticks_per_lot=args.inventory_skew_ticks_per_lot,
        max_market_spread_ticks=args.max_market_spread_ticks,
        max_quotes_per_snapshot=args.max_quotes_per_snapshot,
        max_snapshots=args.max_snapshots,
    )
    print(result.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
