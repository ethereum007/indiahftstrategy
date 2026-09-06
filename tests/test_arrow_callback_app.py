from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brokers.arrow.auth import request_checksum
from brokers.arrow.callback_app import (
    ExchangedToken,
    PostbackJournal,
    create_app,
)
from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowConfigurationError


class Exchange:
    def __init__(self):
        self.calls = []

    async def exchange(self, request_token):
        self.calls.append(request_token)
        return ExchangedToken("private-access-token", "AB1234")


def _client(tmp_path: Path, *, expected_user_id="AB1234"):
    exchange = Exchange()
    config = ArrowConfig(app_id="app-id", app_secret="app-key")
    app = create_app(
        config,
        exchange=exchange,
        journal=PostbackJournal(tmp_path / "postbacks.jsonl"),
        expected_user_id=expected_user_id,
    )
    return TestClient(app), exchange, app


def test_callback_verifies_checksum_exchanges_once_and_never_exposes_token(tmp_path):
    client, exchange, app = _client(tmp_path)
    token = "request-token"
    response = client.get(
        "/auth/callback",
        params={"request-token": token, "checksum": request_checksum("app-id", token)},
    )
    assert response.status_code == 200
    assert "private-access-token" not in response.text
    assert exchange.calls == [token]
    assert app.state.token_store.user_id == "AB1234"
    assert client.get("/healthz").json() == {
        "status": "ok",
        "routing_enabled": False,
        "authenticated": True,
    }
    assert (
        client.get(
            "/auth/callback",
            params={"request-token": token, "checksum": request_checksum("app-id", token)},
        ).status_code
        == 400
    )


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"request-token": "request-token", "checksum": "bad"},
    ],
)
def test_callback_fails_closed_on_missing_or_bad_parameters(tmp_path, params):
    client, _, _ = _client(tmp_path)
    response = client.get("/auth/callback", params=params)
    assert response.status_code == 400
    assert "request-token" not in response.text


def test_callback_fails_closed_on_wrong_arrow_account(tmp_path):
    client, _, _ = _client(tmp_path, expected_user_id="DIFFERENT")
    token = "request-token"
    response = client.get(
        "/auth/callback",
        params={"request-token": token, "checksum": request_checksum("app-id", token)},
    )
    assert response.status_code == 400


def test_postback_is_durable_hash_chained_and_never_routes(tmp_path):
    client, _, _ = _client(tmp_path)
    first = client.post("/order/postback", json={"orderId": "one", "status": "OPEN"})
    second = client.post("/order/postback", json={"orderId": "one", "status": "FILLED"})
    assert first.status_code == 202 and first.json()["routing_enabled"] is False
    assert second.json()["sequence"] == 2
    journal = PostbackJournal(tmp_path / "postbacks.jsonl")
    assert len(journal._read()) == 2


def test_postback_rejects_non_object_and_oversized_payload(tmp_path):
    client, _, _ = _client(tmp_path)
    assert client.post("/order/postback", json=[]).status_code == 400
    assert (
        client.post(
            "/order/postback",
            content=b"{}",
            headers={"content-type": "application/json", "content-length": "1048577"},
        ).status_code
        == 413
    )


def test_callback_app_requires_operator_pinned_arrow_user_id(tmp_path):
    with pytest.raises(ArrowConfigurationError, match="ARROW_EXPECTED_USER_ID"):
        create_app(
            ArrowConfig(app_id="app-id", app_secret="app-key"),
            exchange=Exchange(),
            journal=PostbackJournal(tmp_path / "postbacks.jsonl"),
            expected_user_id="",
        )
