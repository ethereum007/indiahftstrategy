from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from engine.costs import GenericCostModel
from engine.hft_backtest import Instrument, Kind
from markets.profiles import MARKET_PROFILES, MarketProfile, get_market_profile
from reports.manifest import write_experiment_manifest


@dataclass(frozen=True)
class MarketProfileReportConfig:
    markets: tuple[str, ...] = tuple(MARKET_PROFILES)
    price: float | None = None
    qty: int | None = None
    buy_notional_rate: float = 0.0
    sell_notional_rate: float = 0.0
    per_unit_fee: float = 0.0
    per_contract_fee: float = 0.0
    per_order_fee: float = 0.0


@dataclass(frozen=True)
class MarketProfileReport:
    profiles: pd.DataFrame
    cost_examples: pd.DataFrame
    summary: pd.DataFrame
    output_dir: Path | None = None


def build_market_profile_report(config: MarketProfileReportConfig | None = None) -> MarketProfileReport:
    config = config or MarketProfileReportConfig()
    _validate_config(config)
    profiles = [_profile_row(get_market_profile(name)) for name in config.markets]
    profile_frame = pd.DataFrame(profiles)
    costs = _cost_examples(config)
    summary = _summary(profile_frame, costs, config)
    return MarketProfileReport(profiles=profile_frame, cost_examples=costs, summary=summary)


def write_market_profile_report(
    output_dir: str | Path,
    *,
    config: MarketProfileReportConfig | None = None,
) -> MarketProfileReport:
    config = config or MarketProfileReportConfig()
    report = build_market_profile_report(config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    report.profiles.to_csv(out / "market_profiles.csv", index=False)
    report.cost_examples.to_csv(out / "market_cost_examples.csv", index=False)
    report.summary.to_csv(out / "market_profile_summary.csv", index=False)
    write_experiment_manifest(
        out,
        run_type="market_profile_report",
        parameters={"config": asdict(config)},
        inputs={},
    )
    return MarketProfileReport(report.profiles, report.cost_examples, report.summary, out)


def _profile_row(profile: MarketProfile) -> dict[str, object]:
    return {
        "market": profile.name,
        "country": profile.country,
        "currency": profile.currency,
        "session_name": profile.session.name,
        "timezone": profile.session.timezone,
        "open_time": _hhmmss(profile.session.open_seconds),
        "close_time": _hhmmss(profile.session.close_seconds),
        "trading_day_policy": "weekday_only_no_holiday_calendar",
        "trading_weekdays": "|".join(profile.session.trading_weekday_labels),
        "trading_weekday_count": len(profile.session.trading_weekdays),
        "default_tick": float(profile.default_tick),
        "default_lot_size": int(profile.default_lot_size),
        "notes": profile.notes,
    }


def _cost_examples(config: MarketProfileReportConfig) -> pd.DataFrame:
    if config.price is None:
        return pd.DataFrame(
            columns=[
                "market",
                "instrument_kind",
                "price",
                "qty",
                "buy_cost",
                "sell_cost",
                "round_trip_cost",
                "round_trip_bps",
            ]
        )
    costs = GenericCostModel(
        buy_notional_rate=config.buy_notional_rate,
        sell_notional_rate=config.sell_notional_rate,
        per_unit_fee=config.per_unit_fee,
        per_contract_fee=config.per_contract_fee,
        per_order_fee=config.per_order_fee,
    )
    rows = []
    for name in config.markets:
        profile = get_market_profile(name)
        kind = _instrument_kind(profile)
        qty = config.qty if config.qty is not None else profile.default_lot_size
        inst = Instrument(profile.name.upper(), kind, lot_size=profile.default_lot_size, tick=profile.default_tick)
        buy = costs.cost(+1, config.price, qty, inst)
        sell = costs.cost(-1, config.price, qty, inst)
        rows.append(
            {
                "market": profile.name,
                "instrument_kind": kind.value,
                "price": float(config.price),
                "qty": int(qty),
                "buy_cost": float(buy),
                "sell_cost": float(sell),
                "round_trip_cost": float(buy + sell),
                "round_trip_bps": float(costs.round_trip_bps(config.price, inst)),
            }
        )
    return pd.DataFrame(rows)


def _summary(profiles: pd.DataFrame, costs: pd.DataFrame, config: MarketProfileReportConfig) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "markets": int(len(profiles)),
                "countries": int(profiles["country"].nunique()) if not profiles.empty else 0,
                "currencies": int(profiles["currency"].nunique()) if not profiles.empty else 0,
                "weekday_only_markets": int(
                    profiles["trading_day_policy"]
                    .eq("weekday_only_no_holiday_calendar")
                    .sum()
                )
                if not profiles.empty
                else 0,
                "cost_examples": int(len(costs)),
                "explicit_fee_model": bool(config.price is not None),
            }
        ]
    )


def _instrument_kind(profile: MarketProfile) -> Kind:
    if "options" in profile.name or "derivatives" in profile.name:
        return Kind.OPT
    return Kind.EQ


def _hhmmss(seconds: int) -> str:
    hour = seconds // 3600
    minute = (seconds % 3600) // 60
    second = seconds % 60
    return f"{hour:02d}:{minute:02d}:{second:02d}"


def _validate_config(config: MarketProfileReportConfig) -> None:
    if not config.markets:
        raise ValueError("markets must not be empty")
    for name in config.markets:
        get_market_profile(name)
    if config.price is not None and config.price <= 0:
        raise ValueError("price must be positive")
    if config.qty is not None and config.qty <= 0:
        raise ValueError("qty must be positive")
    for field_name in (
        "buy_notional_rate",
        "sell_notional_rate",
        "per_unit_fee",
        "per_contract_fee",
        "per_order_fee",
    ):
        if getattr(config, field_name) < 0:
            raise ValueError(f"{field_name} must be non-negative")
