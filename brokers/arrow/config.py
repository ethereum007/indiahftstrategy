from __future__ import annotations

import os
from dataclasses import dataclass, fields
from urllib.parse import urlparse

from brokers.arrow.errors import ArrowConfigurationError


@dataclass(frozen=True, slots=True)
class ArrowConfig:
    app_id: str = ""
    app_secret: str = ""
    access_token: str = ""
    redirect_url: str = ""
    postback_url: str = ""
    static_ip: str = ""
    api_tier: str = "basic"
    rest_base_url: str = "https://edge.arrow.trade"
    market_data_url: str = "wss://ds.arrow.trade"
    order_stream_url: str = "wss://order-updates.arrow.trade"

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> ArrowConfig:
        env = os.environ if environ is None else environ
        return cls(
            app_id=env.get("ARROW_APP_ID", "").strip(),
            app_secret=env.get("ARROW_APP_SECRET", "").strip(),
            access_token=env.get("ARROW_ACCESS_TOKEN", "").strip(),
            redirect_url=env.get("ARROW_REDIRECT_URL", "").strip(),
            postback_url=env.get("ARROW_POSTBACK_URL", "").strip(),
            static_ip=env.get("ARROW_STATIC_IP", "").strip(),
            api_tier=env.get("ARROW_API_TIER", "basic").strip().lower() or "basic",
        )

    def validate(self, *, require_secret: bool = False, require_static_ip: bool = False) -> None:
        missing = []
        if not self.app_id:
            missing.append("ARROW_APP_ID")
        if require_secret and not self.app_secret:
            missing.append("ARROW_APP_SECRET")
        if require_static_ip and not self.static_ip:
            missing.append("ARROW_STATIC_IP")
        if not self.access_token and not self.app_secret:
            missing.append("ARROW_ACCESS_TOKEN or ARROW_APP_SECRET")
        if missing:
            raise ArrowConfigurationError("missing configuration: " + ", ".join(missing))
        for name in ("rest_base_url", "market_data_url", "order_stream_url"):
            parsed = urlparse(getattr(self, name))
            if parsed.scheme not in {"https", "wss"} or not parsed.netloc:
                raise ArrowConfigurationError(f"{name} must be an https/wss URL")

    def redacted(self) -> dict[str, str]:
        secret_names = {"app_secret", "access_token"}
        return {
            f.name: "***REDACTED***" if f.name in secret_names and getattr(self, f.name) else getattr(self, f.name)
            for f in fields(self)
        }
