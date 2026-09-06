import asyncio

import pytest

from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowConfigurationError
from brokers.arrow.preflight import (
    EndpointProbeResult,
    StaticIpPreflight,
    observe_public_ip,
    parse_public_ip,
    probe_tls_endpoint,
)


async def _public_ip():
    return "8.8.8.8"


async def _reachable(endpoint):
    return EndpointProbeResult(endpoint, True, 2.5)


def test_static_ip_preflight_produces_credential_free_ready_evidence():
    config = ArrowConfig(static_ip="8.8.8.8")
    evidence = asyncio.run(StaticIpPreflight(config, observer=_public_ip, endpoint_probe=_reachable).run())
    assert evidence.ready and evidence.ip_matches
    assert len(evidence.endpoint_results) == 3
    assert "access_token" not in evidence.to_json()


def test_static_ip_preflight_fails_closed_on_mismatch_and_endpoint_failure():
    async def observed():
        return "1.1.1.1"

    async def failed(endpoint):
        return EndpointProbeResult(endpoint, False, None, "TimeoutError")

    evidence = asyncio.run(
        StaticIpPreflight(ArrowConfig(static_ip="8.8.8.8"), observer=observed, endpoint_probe=failed).run()
    )
    assert not evidence.ready and not evidence.ip_matches
    assert evidence.reason_codes == ("static_ip_mismatch", "arrow_endpoint_unreachable")


@pytest.mark.parametrize("value", ["", "not-an-ip", "127.0.0.1", "10.0.0.1"])
def test_static_ip_preflight_rejects_invalid_or_non_public_addresses(value):
    with pytest.raises(ArrowConfigurationError):
        parse_public_ip(value, field="ARROW_STATIC_IP")


def test_public_ip_observer_bounds_and_parses_provider_response(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, limit):
            assert limit == 64
            return b"8.8.8.8\n"

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    assert asyncio.run(observe_public_ip()) == "8.8.8.8"


def test_tls_probe_rejects_bad_url_and_contains_network_errors(monkeypatch):
    invalid = asyncio.run(probe_tls_endpoint("http://unsafe.example"))
    assert not invalid.reachable and invalid.error_type == "invalid_endpoint"

    def timeout(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr("socket.create_connection", timeout)
    failed = asyncio.run(probe_tls_endpoint("https://edge.arrow.trade"))
    assert not failed.reachable and failed.error_type == "TimeoutError"
