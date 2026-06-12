from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from data.chains import load_option_chain_csv
from engine.hft_backtest import IndianCostModel, Instrument, Kind
from reports.manifest import write_experiment_manifest
from research.surface_markouts import compute_surface_markouts, surface_markout_summary


@dataclass(frozen=True)
class SurfaceMMReplayConfig:
    order_latency_us: float = 0.0
    quote_ttl_ns: int = 1_000_000_000
    markout_horizon_ns: int = 1_000_000_000
    fill_depth_fraction: float = 1.0
    lot_size: int = 75
    option_tick: float = 0.05
    contract_multiplier: float = 1.0
    max_quotes: int | None = None
    otr_limit: float = 50.0


@dataclass(frozen=True)
class SurfaceMMReplayResult:
    fills: pd.DataFrame
    unfilled: pd.DataFrame
    equity: pd.DataFrame
    summary: pd.DataFrame
    markouts: pd.DataFrame
    markout_summary: pd.DataFrame
    output_dir: Path | None = None


def run_surface_mm_replay(
    *,
    quotes_path: str | Path,
    chain_path: str | Path,
    output_dir: str | Path | None = None,
    timestamp_unit: str = "ns",
    timestamp_tz: str | None = None,
    filter_session: bool = True,
    config: SurfaceMMReplayConfig | None = None,
) -> SurfaceMMReplayResult:
    config = config or SurfaceMMReplayConfig()
    _validate_config(config)
    quotes_file = Path(quotes_path)
    chain_file = Path(chain_path)
    if not quotes_file.exists():
        raise FileNotFoundError(f"quotes file not found: {quotes_file}")
    if not chain_file.exists():
        raise FileNotFoundError(f"chain file not found: {chain_file}")

    quotes = _normalize_quotes(pd.read_csv(quotes_file), max_quotes=config.max_quotes)
    chain = load_option_chain_csv(
        chain_file,
        timestamp_unit=timestamp_unit,
        timestamp_tz=timestamp_tz,
        filter_session=filter_session,
    ).data
    book = _option_book(chain)
    fills, unfilled = replay_surface_quotes(quotes, book, config=config)
    markouts = _fill_markouts(fills, book, config.markout_horizon_ns)
    fills = _attach_markouts_and_costs(fills, markouts, config)
    equity = _equity_curve(fills)
    summary = _summary(quotes, fills, unfilled, config)
    markout_summary = surface_markout_summary(markouts) if not markouts.empty else _empty_markout_summary()

    out_dir = Path(output_dir) if output_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        quotes.to_csv(out_dir / "quotes.csv", index=False)
        fills.to_csv(out_dir / "fills.csv", index=False)
        unfilled.to_csv(out_dir / "unfilled_quotes.csv", index=False)
        equity.to_csv(out_dir / "equity.csv", index=False)
        summary.to_csv(out_dir / "summary.csv", index=False)
        markouts.to_csv(out_dir / "markouts.csv", index=False)
        markout_summary.to_csv(out_dir / "markout_summary.csv", index=False)
        write_experiment_manifest(
            out_dir,
            run_type="surface_mm_replay",
            inputs={"quotes": quotes_file, "chain": chain_file},
            parameters={
                "timestamp_unit": timestamp_unit,
                "timestamp_tz": timestamp_tz,
                "filter_session": filter_session,
                "config": asdict(config),
            },
        )
    return SurfaceMMReplayResult(fills, unfilled, equity, summary, markouts, markout_summary, out_dir)


def replay_surface_quotes(
    quotes: pd.DataFrame,
    book: pd.DataFrame,
    *,
    config: SurfaceMMReplayConfig | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    config = config or SurfaceMMReplayConfig()
    _validate_config(config)
    _require(quotes, ["quote_id", "ts", "instrument_id", "side", "qty", "price"], "quotes")
    _require(book, ["ts", "instrument_id", "bid", "ask", "bid_qty", "ask_qty", "mid"], "book")

    book = book.sort_values(["instrument_id", "ts"]).reset_index(drop=True)
    order_latency_ns = int(round(config.order_latency_us * 1_000))
    fill_rows = []
    unfilled_rows = []
    option_costs = IndianCostModel.nse_index_options()
    instrument = Instrument(
        "INDEX-OPT",
        Kind.OPT,
        lot_size=config.lot_size,
        tick=config.option_tick,
        multiplier=config.contract_multiplier,
    )

    for quote in quotes.sort_values(["ts", "quote_id"]).itertuples(index=False):
        quote_book = _matching_book(book, quote)
        if quote_book.empty:
            unfilled_rows.append(_unfilled_row(quote, "no_matching_book"))
            continue
        active_ts = int(quote.ts) + order_latency_ns
        expiry_ts = int(quote.ts) + int(config.quote_ttl_ns)
        live_book = quote_book.loc[(quote_book["ts"] >= active_ts) & (quote_book["ts"] <= expiry_ts)]
        if live_book.empty:
            unfilled_rows.append(_unfilled_row(quote, "expired_before_book_update"))
            continue

        touched = _first_touch(live_book, side=int(quote.side), price=float(quote.price))
        if touched is None:
            unfilled_rows.append(_unfilled_row(quote, "no_touch"))
            continue
        contra_qty_col = "ask_qty" if int(quote.side) > 0 else "bid_qty"
        fill_qty = int(min(int(quote.qty), np.floor(float(touched[contra_qty_col]) * config.fill_depth_fraction)))
        if fill_qty <= 0:
            unfilled_rows.append(_unfilled_row(quote, "insufficient_touch_depth"))
            continue
        immediate_markout = float(quote.side) * (float(touched["mid"]) - float(quote.price)) * fill_qty
        cost = option_costs.cost(int(quote.side), float(quote.price), fill_qty, instrument)
        fill_rows.append(
            {
                "quote_id": quote.quote_id,
                "client_order_id": getattr(quote, "client_order_id", ""),
                "quote_ts_ns": int(quote.ts),
                "active_ts_ns": active_ts,
                "ts_ns": int(touched["ts"]),
                "instrument_id": str(quote.instrument_id),
                "expiry": getattr(quote, "expiry", np.nan),
                "strike": getattr(quote, "strike", np.nan),
                "option_type": getattr(quote, "option_type", np.nan),
                "side": int(quote.side),
                "qty": fill_qty,
                "price": float(quote.price),
                "touch_bid": float(touched["bid"]),
                "touch_ask": float(touched["ask"]),
                "touch_mid": float(touched["mid"]),
                "signal_theo": getattr(quote, "theo", np.nan),
                "quote_edge": getattr(quote, "quote_edge", np.nan),
                "maker": True,
                "cost": float(cost),
                "immediate_markout": immediate_markout * config.contract_multiplier,
            }
        )

    fills = pd.DataFrame(fill_rows)
    unfilled = pd.DataFrame(unfilled_rows)
    return (
        fills if not fills.empty else _empty_fills(),
        unfilled if not unfilled.empty else _empty_unfilled(),
    )


def _normalize_quotes(raw: pd.DataFrame, *, max_quotes: int | None) -> pd.DataFrame:
    _require(raw, ["instrument_id", "side", "qty", "price"], "quotes")
    frame = raw.copy().reset_index(drop=True)
    ts_col = _first_present(frame, ["ts", "ts_signal_ns", "quote_ts_ns"])
    if ts_col is None:
        raise ValueError("quotes missing required timestamp column: one of ['ts', 'ts_signal_ns', 'quote_ts_ns']")
    frame["ts"] = pd.to_numeric(frame[ts_col], errors="coerce").astype("int64")
    frame["instrument_id"] = frame["instrument_id"].astype(str)
    frame["side"] = frame["side"].map(_normalize_side).astype("int64")
    frame["qty"] = pd.to_numeric(frame["qty"], errors="coerce").astype("int64")
    frame["price"] = pd.to_numeric(frame["price"], errors="coerce").astype("float64")
    if "quote_id" not in frame.columns:
        if "client_order_id" in frame.columns:
            frame["quote_id"] = frame["client_order_id"].fillna("").astype(str)
            blank = frame["quote_id"].str.len() == 0
            frame.loc[blank, "quote_id"] = [f"Q{idx:06d}" for idx in frame.loc[blank].index]
        else:
            frame["quote_id"] = [f"Q{idx:06d}" for idx in frame.index]
    if "client_order_id" not in frame.columns:
        frame["client_order_id"] = frame["quote_id"]
    if "strike" not in frame.columns or "option_type" not in frame.columns:
        parsed = frame["instrument_id"].map(_parse_instrument_id)
        if "strike" not in frame.columns:
            frame["strike"] = [item[1] for item in parsed]
        if "option_type" not in frame.columns:
            frame["option_type"] = [item[0] for item in parsed]
    frame["option_type"] = frame["option_type"].astype(str).str.upper()
    if "expiry" not in frame.columns:
        frame["expiry"] = np.nan
    if "theo" not in frame.columns:
        frame["theo"] = np.nan
    if "quote_edge" not in frame.columns:
        frame["quote_edge"] = np.where(
            frame["side"] > 0,
            frame["theo"].astype(float) - frame["price"],
            frame["price"] - frame["theo"].astype(float),
        )
    frame = frame.loc[(frame["side"].isin([-1, 1])) & (frame["qty"] > 0) & (frame["price"] > 0)].copy()
    frame = frame.sort_values(["ts", "quote_id"]).reset_index(drop=True)
    if max_quotes is not None:
        frame = frame.head(max_quotes).copy()
    return frame


def _option_book(chain: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in chain.itertuples(index=False):
        strike = float(row.strike)
        strike_label = _strike_label(strike)
        rows.extend(
            [
                {
                    "ts": int(row.ts),
                    "expiry": row.expiry,
                    "instrument_id": f"CALL_{strike_label}",
                    "strike": strike,
                    "option_type": "C",
                    "bid": float(row.call_bid),
                    "ask": float(row.call_ask),
                    "bid_qty": int(row.call_bid_qty),
                    "ask_qty": int(row.call_ask_qty),
                    "regime": getattr(row, "regime", np.nan),
                },
                {
                    "ts": int(row.ts),
                    "expiry": row.expiry,
                    "instrument_id": f"PUT_{strike_label}",
                    "strike": strike,
                    "option_type": "P",
                    "bid": float(row.put_bid),
                    "ask": float(row.put_ask),
                    "bid_qty": int(row.put_bid_qty),
                    "ask_qty": int(row.put_ask_qty),
                    "regime": getattr(row, "regime", np.nan),
                },
            ]
        )
    book = pd.DataFrame(rows)
    if book.empty:
        return pd.DataFrame(columns=["ts", "expiry", "instrument_id", "strike", "option_type", "bid", "ask", "bid_qty", "ask_qty", "mid"])
    book["mid"] = 0.5 * (book["bid"] + book["ask"])
    return book.sort_values(["instrument_id", "ts"]).reset_index(drop=True)


def _matching_book(book: pd.DataFrame, quote: object) -> pd.DataFrame:
    mask = book["instrument_id"] == str(quote.instrument_id)
    quote_expiry = getattr(quote, "expiry", np.nan)
    if not pd.isna(quote_expiry) and "expiry" in book.columns:
        mask &= book["expiry"].astype(str) == str(quote_expiry)
    return book.loc[mask].copy()


def _first_touch(book: pd.DataFrame, *, side: int, price: float) -> pd.Series | None:
    if side > 0:
        touched = book.loc[book["ask"] <= price]
    else:
        touched = book.loc[book["bid"] >= price]
    if touched.empty:
        return None
    return touched.iloc[0]


def _fill_markouts(fills: pd.DataFrame, book: pd.DataFrame, horizon_ns: int) -> pd.DataFrame:
    if fills.empty:
        return _empty_markouts()
    surface_values = book.rename(columns={"mid": "theo"})[["ts", "instrument_id", "theo"]]
    markouts = compute_surface_markouts(fills, surface_values, horizons_ns=[horizon_ns])
    if markouts.empty:
        return _empty_markouts()
    markouts["markout"] = markouts["surface_markout"]
    markouts["net_markout"] = markouts["markout"] - markouts["cost"].fillna(0.0)
    return markouts


def _attach_markouts_and_costs(
    fills: pd.DataFrame,
    markouts: pd.DataFrame,
    config: SurfaceMMReplayConfig,
) -> pd.DataFrame:
    if fills.empty:
        return fills
    out = fills.sort_values(["ts_ns", "quote_id"]).reset_index(drop=True).copy()
    if markouts.empty:
        out["markout"] = out["immediate_markout"]
    else:
        markout_by_fill = markouts.drop_duplicates("fill_id").set_index("fill_id")["markout"]
        out["markout"] = out.index.map(markout_by_fill).astype(float)
        out["markout"] = out["markout"].fillna(out["immediate_markout"])
    out["gross_pnl"] = out["markout"] * config.contract_multiplier
    out["net_pnl"] = out["gross_pnl"] - out["cost"]
    return out


def _equity_curve(fills: pd.DataFrame) -> pd.DataFrame:
    if fills.empty:
        return pd.DataFrame(columns=["ts", "equity"])
    ordered = fills.sort_values(["ts_ns", "quote_id"]).copy()
    ordered["equity"] = ordered["net_pnl"].cumsum()
    return ordered.rename(columns={"ts_ns": "ts"})[["ts", "equity"]].reset_index(drop=True)


def _summary(
    quotes: pd.DataFrame,
    fills: pd.DataFrame,
    unfilled: pd.DataFrame,
    config: SurfaceMMReplayConfig,
) -> pd.DataFrame:
    orders_sent = int(len(quotes))
    fill_events = int(len(fills))
    filled_qty = int(fills["qty"].sum()) if fill_events else 0
    quoted_qty = int(quotes["qty"].sum()) if orders_sent else 0
    turnover = float((fills["qty"] * fills["price"] * config.contract_multiplier).sum()) if fill_events else 0.0
    total_costs = float(fills["cost"].sum()) if fill_events else 0.0
    gross_pnl = float(fills["gross_pnl"].sum()) if fill_events else 0.0
    net_pnl = float(fills["net_pnl"].sum()) if fill_events else 0.0
    otr = orders_sent / max(fill_events, 1)
    return pd.DataFrame(
        [
            {
                "net_pnl": net_pnl,
                "gross_pnl": gross_pnl,
                "total_costs": total_costs,
                "orders_sent": orders_sent,
                "fills": fill_events,
                "unfilled_quotes": int(len(unfilled)),
                "fill_rate": fill_events / orders_sent if orders_sent else 0.0,
                "quoted_qty": quoted_qty,
                "filled_qty": filled_qty,
                "qty_fill_rate": filled_qty / quoted_qty if quoted_qty else 0.0,
                "order_to_trade_ratio": float(otr),
                "otr_limit": float(config.otr_limit),
                "otr_breached": bool(otr > config.otr_limit),
                "turnover": turnover,
                "cost_bps": 1e4 * total_costs / turnover if turnover > 0 else np.nan,
                "maker_share": 1.0 if fill_events else 0.0,
                "markout_horizon_ns": int(config.markout_horizon_ns),
                "quote_ttl_ns": int(config.quote_ttl_ns),
                "fill_depth_fraction": float(config.fill_depth_fraction),
            }
        ]
    )


def _unfilled_row(quote: object, reason: str) -> dict[str, object]:
    return {
        "quote_id": quote.quote_id,
        "client_order_id": getattr(quote, "client_order_id", ""),
        "quote_ts_ns": int(quote.ts),
        "instrument_id": str(quote.instrument_id),
        "expiry": getattr(quote, "expiry", np.nan),
        "strike": getattr(quote, "strike", np.nan),
        "option_type": getattr(quote, "option_type", np.nan),
        "side": int(quote.side),
        "qty": int(quote.qty),
        "price": float(quote.price),
        "unfilled_reason": reason,
    }


def _validate_config(config: SurfaceMMReplayConfig) -> None:
    if config.order_latency_us < 0:
        raise ValueError("order_latency_us must be non-negative")
    if config.quote_ttl_ns < 0:
        raise ValueError("quote_ttl_ns must be non-negative")
    if config.markout_horizon_ns < 0:
        raise ValueError("markout_horizon_ns must be non-negative")
    if config.fill_depth_fraction <= 0:
        raise ValueError("fill_depth_fraction must be positive")
    if config.lot_size <= 0:
        raise ValueError("lot_size must be positive")
    if config.option_tick <= 0:
        raise ValueError("option_tick must be positive")
    if config.contract_multiplier <= 0:
        raise ValueError("contract_multiplier must be positive")
    if config.max_quotes is not None and config.max_quotes < 0:
        raise ValueError("max_quotes must be non-negative")
    if config.otr_limit <= 0:
        raise ValueError("otr_limit must be positive")


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [col for col in columns if col not in frame.columns]
    if missing:
        raise ValueError(f"{name} missing required columns: {missing}")


def _first_present(frame: pd.DataFrame, columns: list[str]) -> str | None:
    for col in columns:
        if col in frame.columns:
            return col
    return None


def _normalize_side(value: object) -> int:
    if pd.isna(value):
        return 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "+1", "b", "buy", "bid"}:
            return 1
        if normalized in {"-1", "s", "sell", "ask"}:
            return -1
        return 0
    numeric = float(value)
    if numeric > 0:
        return 1
    if numeric < 0:
        return -1
    return 0


def _parse_instrument_id(instrument_id: str) -> tuple[str | float, float]:
    text = str(instrument_id).upper()
    if text.startswith("CALL_"):
        return "C", float(text.replace("CALL_", "").replace("_", "."))
    if text.startswith("PUT_"):
        return "P", float(text.replace("PUT_", "").replace("_", "."))
    return np.nan, np.nan


def _strike_label(strike: float) -> str:
    return str(float(strike)).replace(".", "_")


def _empty_fills() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "quote_id",
            "client_order_id",
            "quote_ts_ns",
            "active_ts_ns",
            "ts_ns",
            "instrument_id",
            "expiry",
            "strike",
            "option_type",
            "side",
            "qty",
            "price",
            "touch_bid",
            "touch_ask",
            "touch_mid",
            "signal_theo",
            "quote_edge",
            "maker",
            "cost",
            "immediate_markout",
            "markout",
            "gross_pnl",
            "net_pnl",
        ]
    )


def _empty_unfilled() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "quote_id",
            "client_order_id",
            "quote_ts_ns",
            "instrument_id",
            "expiry",
            "strike",
            "option_type",
            "side",
            "qty",
            "price",
            "unfilled_reason",
        ]
    )


def _empty_markouts() -> pd.DataFrame:
    return pd.DataFrame(columns=["fill_id", "horizon_ns", "markout", "net_markout"])


def _empty_markout_summary() -> pd.DataFrame:
    return pd.DataFrame(columns=["horizon_ns", "count", "surface_markout_mean", "surface_markout_median", "win_rate"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay passive surface market-making quotes.")
    parser.add_argument("--quotes", required=True)
    parser.add_argument("--chain", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--timestamp-unit", default="ns", choices=["ns", "us", "ms", "s", "datetime"])
    parser.add_argument("--timestamp-tz", default=None)
    parser.add_argument("--no-filter-session", action="store_true")
    parser.add_argument("--order-latency-us", type=float, default=0.0)
    parser.add_argument("--quote-ttl-ns", type=int, default=1_000_000_000)
    parser.add_argument("--markout-horizon-ns", type=int, default=1_000_000_000)
    parser.add_argument("--fill-depth-fraction", type=float, default=1.0)
    parser.add_argument("--lot-size", type=int, default=75)
    parser.add_argument("--option-tick", type=float, default=0.05)
    parser.add_argument("--contract-multiplier", type=float, default=1.0)
    parser.add_argument("--max-quotes", type=int, default=None)
    args = parser.parse_args(argv)
    result = run_surface_mm_replay(
        quotes_path=args.quotes,
        chain_path=args.chain,
        output_dir=args.out,
        timestamp_unit=args.timestamp_unit,
        timestamp_tz=args.timestamp_tz,
        filter_session=not args.no_filter_session,
        config=SurfaceMMReplayConfig(
            order_latency_us=args.order_latency_us,
            quote_ttl_ns=args.quote_ttl_ns,
            markout_horizon_ns=args.markout_horizon_ns,
            fill_depth_fraction=args.fill_depth_fraction,
            lot_size=args.lot_size,
            option_tick=args.option_tick,
            contract_multiplier=args.contract_multiplier,
            max_quotes=args.max_quotes,
        ),
    )
    print(result.summary.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
