import asyncio
import base64
import hashlib
import json
from datetime import datetime, timezone

import pytest

from brokers.arrow.auth import ArrowAuthManager, AuthState, request_checksum, token_exchange_checksum
from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowAuthenticationError, ArrowConfigurationError
from brokers.arrow.telemetry import redact


def _jwt(exp):
    body = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"x.{body}.x"


def test_official_checksums_and_redaction():
    assert request_checksum("app", "request") == hashlib.sha256(b"request:app").hexdigest()
    assert token_exchange_checksum("app", "secret", "request") == hashlib.sha256(b"app:secret:request").hexdigest()
    assert redact({"token": "secret", "nested": {"app_secret": "hidden"}}) == {
        "token": "***REDACTED***",
        "nested": {"app_secret": "***REDACTED***"},
    }


def test_config_and_expired_token_fail_closed():
    with pytest.raises(ArrowConfigurationError):
        ArrowConfig().validate()
    with pytest.raises(ArrowConfigurationError, match="ARROW_STATIC_IP"):
        ArrowConfig(app_id="app", access_token="opaque").validate(require_static_ip=True)
    cfg = ArrowConfig(app_id="app", access_token=_jwt(1))
    auth = ArrowAuthManager(cfg)
    with pytest.raises(ArrowAuthenticationError):
        asyncio.run(auth.authenticate())
    assert auth.state == AuthState.EXPIRED


def test_empty_env_example_contract():
    cfg = ArrowConfig.from_env({"ARROW_APP_ID": " A ", "ARROW_ACCESS_TOKEN": " t "})
    assert cfg.app_id == "A" and cfg.redacted()["access_token"] == "***REDACTED***"
