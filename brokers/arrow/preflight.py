from __future__ import annotations

import argparse
import asyncio
import json
import socket
import ssl
import time
import urllib.request
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address, IPv6Address, ip_address
from urllib.parse import urlparse

from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowConfigurationError

IpAddress = IPv4Address | IPv6Address
PublicIpObserver = Callable[[], Awaitable[str]]
EndpointProbe = Callable[[str], Awaitable["EndpointProbeResult"]]


@dataclass(frozen=True, slots=True)
class EndpointProbeResult:
    endpoint: str
    reachable: bool
    latency_ms: float | None
    error_type: str = ""


@dataclass(frozen=True, slots=True)
class StaticIpPreflightEvidence:
    configured_ip: str
    observed_ip: str
    ip_matches: bool
    endpoint_results: tuple[EndpointProbeResult, ...]
    checked_ts: datetime
    ready: bool
    reason_codes: tuple[str, ...]

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=lambda value: value.isoformat(), indent=2, sort_keys=True)


def parse_public_ip(value: str, *, field: str) -> IpAddress:
    try:
        parsed = ip_address(value.strip())
    except ValueError as exc:
        raise ArrowConfigurationError(f"{field} must be a valid IP address") from exc
    if not parsed.is_global:
        raise ArrowConfigurationError(f"{field} must be a public globally routable IP address")
    return parsed


async def observe_public_ip(*, timeout_seconds: float = 5.0) -> str:
    def fetch() -> str:
        with urllib.request.urlopen("https://api.ipify.org", timeout=timeout_seconds) as response:  # nosec B310
            return response.read(64).decode("ascii").strip()

    return await asyncio.to_thread(fetch)


async def probe_tls_endpoint(endpoint: str, *, timeout_seconds: float = 5.0) -> EndpointProbeResult:
    parsed = urlparse(endpoint)
    host = parsed.hostname
    if not host or parsed.scheme not in {"https", "wss"}:
        return EndpointProbeResult(endpoint, False, None, "invalid_endpoint")
    port = parsed.port or 443

    def probe() -> float:
        started = time.perf_counter_ns()
        context = ssl.create_default_context()
        with (
            socket.create_connection((host, port), timeout=timeout_seconds) as connection,
            context.wrap_socket(connection, server_hostname=host),
        ):
            pass
        return (time.perf_counter_ns() - started) / 1_000_000

    try:
        latency_ms = await asyncio.to_thread(probe)
        return EndpointProbeResult(endpoint, True, latency_ms)
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        return EndpointProbeResult(endpoint, False, None, type(exc).__name__)


class StaticIpPreflight:
    """Credential-free proof that the configured static egress path is in use."""

    def __init__(
        self,
        config: ArrowConfig,
        *,
        observer: PublicIpObserver = observe_public_ip,
        endpoint_probe: EndpointProbe = probe_tls_endpoint,
        endpoints: Sequence[str] | None = None,
    ) -> None:
        self.config = config
        self.observer = observer
        self.endpoint_probe = endpoint_probe
        self.endpoints = tuple(endpoints or (config.rest_base_url, config.market_data_url, config.order_stream_url))

    async def run(self) -> StaticIpPreflightEvidence:
        configured = parse_public_ip(self.config.static_ip, field="ARROW_STATIC_IP")
        observed_text = await self.observer()
        observed = parse_public_ip(observed_text, field="observed egress IP")
        results = tuple(await asyncio.gather(*(self.endpoint_probe(endpoint) for endpoint in self.endpoints)))
        reasons: list[str] = []
        if configured != observed:
            reasons.append("static_ip_mismatch")
        if any(not result.reachable for result in results):
            reasons.append("arrow_endpoint_unreachable")
        reason_codes = tuple(reasons)
        return StaticIpPreflightEvidence(
            str(configured),
            str(observed),
            configured == observed,
            results,
            datetime.now(UTC),
            not reason_codes,
            reason_codes,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Credential-free Arrow static-IP connectivity preflight")
    parser.add_argument("--output", help="Optional path for the JSON evidence artifact")
    args = parser.parse_args()
    try:
        evidence = asyncio.run(StaticIpPreflight(ArrowConfig.from_env()).run())
    except ArrowConfigurationError as exc:
        parser.error(str(exc))
    rendered = evidence.to_json()
    if args.output:
        from pathlib import Path

        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if evidence.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
