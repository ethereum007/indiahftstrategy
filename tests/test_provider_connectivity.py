from __future__ import annotations

import pytest

from provider_connectivity import (
    ProviderConnectivityError,
    ProviderConnectivityOutcome,
    execute_provider_connectivity_probe,
    load_provider_connectivity_backend,
    resolve_provider_connectivity_backend_entrypoint,
    validate_connectivity_endpoint,
)


def _probe(**overrides):
    values = {
        "provider": "arrow_money",
        "adapter": "arrow_ws",
        "transport": "websocket",
        "endpoint": "wss://feed.arrow.money/market-data/nse",
        "market": "india_nse_index_derivatives",
        "exchange": "NSE",
        "session_id": "nse-live-dryrun-20260714",
        "handoff_id": "handoff-1",
        "plan_sha256": "a" * 64,
        "credential_env_vars": (
            "ARROW_MONEY_API_KEY",
            "ARROW_MONEY_API_SECRET",
        ),
        "backend_entrypoint": "tests.fake_connectivity:probe",
        "environ": {
            "ARROW_MONEY_API_KEY": "key-value-that-must-not-be-stored",
            "ARROW_MONEY_API_SECRET": "secret-value-that-must-not-be-stored",
        },
    }
    values.update(overrides)
    return execute_provider_connectivity_probe(**values)


def test_connectivity_probe_exposes_only_credential_presence_to_backend():
    captured = {}

    def backend(request):
        captured["request"] = request
        return ProviderConnectivityOutcome(
            connected=True,
            authenticated=True,
            market_data_readable=True,
            protocol="WebSocket",
        )

    result = _probe(backend=backend)

    assert result.passed
    assert result.outcome.protocol == "websocket"
    assert result.request.credential_env_presence == {
        "ARROW_MONEY_API_KEY": True,
        "ARROW_MONEY_API_SECRET": True,
    }
    assert captured["request"] is result.request
    serialized = repr(result)
    assert "key-value-that-must-not-be-stored" not in serialized
    assert "secret-value-that-must-not-be-stored" not in serialized


def test_connectivity_probe_rejects_missing_credentials_before_backend_call():
    called = False

    def backend(_request):
        nonlocal called
        called = True
        return ProviderConnectivityOutcome(True, True, True)

    with pytest.raises(
        ProviderConnectivityError,
        match="ARROW_MONEY_API_SECRET",
    ):
        _probe(
            backend=backend,
            environ={"ARROW_MONEY_API_KEY": "present"},
        )

    assert not called


@pytest.mark.parametrize(
    ("endpoint", "transport"),
    [
        ("ws://feed.example.test/ticks", "websocket"),
        ("wss://user:password@feed.example.test/ticks", "websocket"),
        ("wss://feed.example.test/ticks?token=secret", "websocket"),
        ("wss://feed.example.test/ticks?version=1", "websocket"),
        ("wss://feed.example.test/ticks#credential", "websocket"),
        ("http://feed.example.test/ticks", "rest"),
    ],
)
def test_connectivity_endpoint_rejects_insecure_or_credential_bearing_urls(
    endpoint,
    transport,
):
    assert validate_connectivity_endpoint(endpoint, transport)


def test_connectivity_probe_reduces_backend_failures_to_safe_codes():
    leaked_message = "credential-value-must-not-escape"

    def backend(_request):
        raise RuntimeError(leaked_message)

    result = _probe(backend=backend)

    assert not result.passed
    assert result.probe_called
    assert result.outcome.error_code == "backend_exception_runtimeerror"
    assert leaked_message not in repr(result)


def test_connectivity_probe_blocks_invalid_backend_outcome():
    result = _probe(backend=lambda _request: {"connected": True})

    assert not result.passed
    assert result.outcome.error_code == "invalid_backend_outcome"


def test_connectivity_backend_configuration_is_provider_scoped_and_strict():
    assert (
        resolve_provider_connectivity_backend_entrypoint(
            "arrow_money",
            environ={
                "ARROW_MONEY_PROVIDER_CONNECTIVITY_BACKEND": "trusted:probe",
                "PROVIDER_CONNECTIVITY_BACKEND": "fallback:probe",
            },
        )
        == "trusted:probe"
    )
    with pytest.raises(ProviderConnectivityError, match="module:function"):
        load_provider_connectivity_backend("trusted:probe.attribute")
