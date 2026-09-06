from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Protocol

from brokers.arrow.errors import ArrowRateLimitError


@dataclass(frozen=True, slots=True)
class EndpointLimit:
    per_minute: int
    burst: int
    daily: int | None = None


@dataclass(frozen=True, slots=True)
class RateLimitProfile:
    name: str
    endpoints: dict[str, EndpointLimit] = field(default_factory=dict)


class ConfigurableRateLimiter:
    def __init__(self, profile: RateLimitProfile, clock=time.monotonic) -> None:
        self.profile = profile
        self.clock = clock
        self._minute: dict[str, deque[float]] = defaultdict(deque)
        self._burst: dict[str, deque[float]] = defaultdict(deque)
        self._daily: dict[str, int] = defaultdict(int)
        self._retry_after: dict[str, float] = {}

    def acquire(self, endpoint_class: str) -> None:
        limit = self.profile.endpoints.get(endpoint_class)
        if limit is None:
            raise ArrowRateLimitError(f"no configured limit for endpoint class {endpoint_class}")
        now = self.clock()
        if now < self._retry_after.get(endpoint_class, 0):
            raise ArrowRateLimitError("endpoint is in Retry-After backoff")
        minute, burst = self._minute[endpoint_class], self._burst[endpoint_class]
        while minute and now - minute[0] >= 60:
            minute.popleft()
        while burst and now - burst[0] >= 1:
            burst.popleft()
        if len(minute) >= limit.per_minute or len(burst) >= limit.burst:
            raise ArrowRateLimitError("configured rate limit exhausted")
        if limit.daily is not None and self._daily[endpoint_class] >= limit.daily:
            raise ArrowRateLimitError("configured daily quota exhausted")
        minute.append(now)
        burst.append(now)
        self._daily[endpoint_class] += 1

    def observe_429(self, endpoint_class: str, retry_after_seconds: float) -> None:
        self._retry_after[endpoint_class] = self.clock() + max(0.0, retry_after_seconds)

    def pressure(self, endpoint_class: str) -> float:
        limit = self.profile.endpoints[endpoint_class]
        return max(len(self._minute[endpoint_class]) / limit.per_minute, len(self._burst[endpoint_class]) / limit.burst)


class HaltController(Protocol):
    def trigger(self, reason: str) -> object: ...


@dataclass(slots=True)
class RateLimitCircuitBreaker:
    limiter: ConfigurableRateLimiter
    kill_switch: HaltController
    danger_threshold: float = 0.9

    def assess(self, endpoint_class: str) -> float:
        if not 0 < self.danger_threshold <= 1:
            raise ValueError("danger threshold must be in (0, 1]")
        pressure = self.limiter.pressure(endpoint_class)
        if pressure >= self.danger_threshold:
            self.kill_switch.trigger("rate_limit_danger")
        return pressure


def profile_from_config(name: str, config: dict[str, dict[str, int | None]]) -> RateLimitProfile:
    """Build profiles from reviewed configuration; no undocumented limits are baked in."""
    endpoints = {}
    for key, values in config.items():
        per_minute = values.get("per_minute")
        burst = values.get("burst")
        if per_minute is None or burst is None:
            raise ValueError("per_minute and burst are required")
        endpoints[key] = EndpointLimit(per_minute, burst, values.get("daily"))
    return RateLimitProfile(name, endpoints)
