from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

import pandas as pd


REGULAR_TRADING_WEEKDAYS = (0, 1, 2, 3, 4)
WEEKDAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _parse_hhmmss(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError("time must be HH:MM:SS")
    hour, minute, second = (int(part) for part in parts)
    if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
        raise ValueError("invalid wall-clock time")
    return hour * 3600 + minute * 60 + second


@dataclass(frozen=True)
class SessionSpec:
    name: str
    timezone: str
    open_seconds: int
    close_seconds: int
    trading_weekdays: tuple[int, ...] = REGULAR_TRADING_WEEKDAYS

    @classmethod
    def from_hhmmss(
        cls,
        name: str,
        timezone: str,
        open_time: str,
        close_time: str,
        trading_weekdays: tuple[int, ...] = REGULAR_TRADING_WEEKDAYS,
    ) -> "SessionSpec":
        weekdays = tuple(int(day) for day in trading_weekdays)
        if not weekdays or len(set(weekdays)) != len(weekdays):
            raise ValueError("trading_weekdays must contain unique weekday numbers")
        if any(day < 0 or day > 6 for day in weekdays):
            raise ValueError("trading weekdays must be between 0 and 6")
        return cls(
            name=name,
            timezone=timezone,
            open_seconds=_parse_hhmmss(open_time),
            close_seconds=_parse_hhmmss(close_time),
            trading_weekdays=weekdays,
        )

    def local_datetimes(self, ts_ns: pd.Series) -> pd.Series:
        return pd.to_datetime(ts_ns, unit="ns", utc=True).dt.tz_convert(
            ZoneInfo(self.timezone)
        )

    def time_mask(self, ts_ns: pd.Series) -> pd.Series:
        dt = self.local_datetimes(ts_ns)
        seconds = dt.dt.hour * 3600 + dt.dt.minute * 60 + dt.dt.second
        return (seconds >= self.open_seconds) & (seconds <= self.close_seconds)

    def trading_day_mask(self, ts_ns: pd.Series) -> pd.Series:
        dt = self.local_datetimes(ts_ns)
        return dt.dt.dayofweek.isin(self.trading_weekdays)

    def mask(self, ts_ns: pd.Series) -> pd.Series:
        return self.time_mask(ts_ns) & self.trading_day_mask(ts_ns)

    @property
    def trading_weekday_labels(self) -> tuple[str, ...]:
        return tuple(WEEKDAY_LABELS[day] for day in self.trading_weekdays)


@dataclass(frozen=True)
class MarketProfile:
    name: str
    country: str
    currency: str
    session: SessionSpec
    default_tick: float
    default_lot_size: int
    notes: str = ""


INDIA_NSE_INDEX_DERIVATIVES = MarketProfile(
    name="india_nse_index_derivatives",
    country="IN",
    currency="INR",
    session=SessionSpec.from_hhmmss(
        "NSE regular session",
        "Asia/Kolkata",
        "09:15:00",
        "15:30:00",
    ),
    default_tick=0.05,
    default_lot_size=75,
    notes="India-first default for Nifty/Sensex index derivatives research.",
)

US_EQUITIES_REGULAR = MarketProfile(
    name="us_equities_regular",
    country="US",
    currency="USD",
    session=SessionSpec.from_hhmmss(
        "US equities regular session",
        "America/New_York",
        "09:30:00",
        "16:00:00",
    ),
    default_tick=0.01,
    default_lot_size=1,
    notes="US regular trading hours profile; fees should be supplied explicitly.",
)

US_OPTIONS_REGULAR = MarketProfile(
    name="us_options_regular",
    country="US",
    currency="USD",
    session=SessionSpec.from_hhmmss(
        "US options regular session",
        "America/New_York",
        "09:30:00",
        "16:00:00",
    ),
    default_tick=0.01,
    default_lot_size=100,
    notes="US listed-options profile; OCC/exchange/broker fees are configurable.",
)

MARKET_PROFILES = {
    INDIA_NSE_INDEX_DERIVATIVES.name: INDIA_NSE_INDEX_DERIVATIVES,
    US_EQUITIES_REGULAR.name: US_EQUITIES_REGULAR,
    US_OPTIONS_REGULAR.name: US_OPTIONS_REGULAR,
}


def get_market_profile(name: str) -> MarketProfile:
    try:
        return MARKET_PROFILES[name]
    except KeyError as exc:
        raise ValueError(f"unknown market profile {name!r}; known profiles: {sorted(MARKET_PROFILES)}") from exc


def session_mask(ts_ns: pd.Series, *, market: str = INDIA_NSE_INDEX_DERIVATIVES.name) -> pd.Series:
    return get_market_profile(market).session.mask(ts_ns)


def session_time_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> pd.Series:
    return get_market_profile(market).session.time_mask(ts_ns)


def trading_day_mask(
    ts_ns: pd.Series,
    *,
    market: str = INDIA_NSE_INDEX_DERIVATIVES.name,
) -> pd.Series:
    return get_market_profile(market).session.trading_day_mask(ts_ns)
