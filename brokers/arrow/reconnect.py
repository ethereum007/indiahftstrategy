from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    initial_seconds: float = 0.25
    maximum_seconds: float = 30.0
    multiplier: float = 2.0
    jitter_fraction: float = 0.2
    max_attempts: int = 12

    def delay(self, attempt: int, *, random_value: float | None = None) -> float:
        if attempt < 0 or attempt >= self.max_attempts:
            raise ValueError("reconnect attempt outside policy")
        base = min(self.maximum_seconds, self.initial_seconds * self.multiplier**attempt)
        draw = random.random() if random_value is None else random_value  # nosec B311 - non-security jitter
        return max(0.0, base * (1 + self.jitter_fraction * (2 * draw - 1)))
