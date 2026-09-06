from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse

from brokers.arrow.auth import request_checksum, token_exchange_checksum
from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowAuthenticationError, ArrowConfigurationError

MAX_POSTBACK_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class ExchangedToken:
    access_token: str
    user_id: str


class TokenExchange(Protocol):
    async def exchange(self, request_token: str) -> ExchangedToken: ...


class ArrowTokenExchangeClient:
    def __init__(self, config: ArrowConfig, *, timeout_seconds: float = 10.0) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    async def exchange(self, request_token: str) -> ExchangedToken:
        payload = json.dumps(
            {
                "checkSum": token_exchange_checksum(
                    self.config.app_id,
                    self.config.app_secret,
                    request_token,
                ),
                "token": request_token,
                "appID": self.config.app_id,
            }
        ).encode()
        endpoint = f"{self.config.rest_base_url.rstrip('/')}/auth/app/authenticate-token"

        def send() -> ExchangedToken:
            request = urllib.request.Request(  # nosec B310 - fixed validated HTTPS Arrow endpoint
                endpoint,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:  # nosec B310
                    body = json.loads(response.read(MAX_POSTBACK_BYTES))
            except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                raise ArrowAuthenticationError("Arrow token exchange failed") from exc
            data = body.get("data") if isinstance(body, dict) else None
            token = data.get("token") if isinstance(data, dict) else None
            user_id = data.get("userId") if isinstance(data, dict) else None
            if not isinstance(token, str) or not token or not isinstance(user_id, str) or not user_id:
                raise ArrowAuthenticationError("Arrow token exchange returned an invalid response")
            return ExchangedToken(token, user_id)

        return await asyncio.to_thread(send)


@dataclass(slots=True)
class RuntimeTokenStore:
    access_token: str = ""
    user_id: str = ""
    issued_ts: datetime | None = None

    def replace(self, exchanged: ExchangedToken) -> None:
        self.access_token = exchanged.access_token
        self.user_id = exchanged.user_id
        self.issued_ts = datetime.now(UTC)


class AuthCallbackCoordinator:
    def __init__(
        self,
        config: ArrowConfig,
        exchange: TokenExchange,
        store: RuntimeTokenStore,
        *,
        expected_user_id: str = "",
    ) -> None:
        if not config.app_id or not config.app_secret:
            raise ArrowConfigurationError("ARROW_APP_ID and ARROW_APP_SECRET are required")
        self.config = config
        self.exchange = exchange
        self.store = store
        self.expected_user_id = expected_user_id
        self._consumed_tokens: set[str] = set()

    async def accept(self, request_token: str, checksum: str) -> str:
        if not request_token or not checksum:
            raise ArrowAuthenticationError("missing callback parameters")
        expected = request_checksum(self.config.app_id, request_token)
        if not hmac.compare_digest(expected, checksum.lower()):
            raise ArrowAuthenticationError("invalid callback checksum")
        fingerprint = hashlib.sha256(request_token.encode()).hexdigest()
        if fingerprint in self._consumed_tokens:
            raise ArrowAuthenticationError("callback token was already consumed")
        exchanged = await self.exchange.exchange(request_token)
        if self.expected_user_id and not hmac.compare_digest(exchanged.user_id, self.expected_user_id):
            raise ArrowAuthenticationError("authenticated Arrow account does not match configured account")
        self._consumed_tokens.add(fingerprint)
        self.store.replace(exchanged)
        return exchanged.user_id


class PostbackJournal:
    """Durable hash-chained raw evidence pending live Arrow schema certification."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append(self, payload: Mapping[str, Any], *, source: str) -> int:
        with self._lock:
            return self._append_locked(payload, source=source)

    def _append_locked(self, payload: Mapping[str, Any], *, source: str) -> int:
        rows = self._read()
        previous_hash = str(rows[-1]["event_hash"]) if rows else ""
        sequence = len(rows) + 1
        body = {
            "sequence": sequence,
            "received_ts": datetime.now(UTC).isoformat(),
            "source": source,
            "previous_hash": previous_hash,
            "payload": payload,
        }
        canonical = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str)
        row = {**body, "event_hash": hashlib.sha256(canonical.encode()).hexdigest()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch(mode=0o600)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, separators=(",", ":"), sort_keys=True, default=str) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return sequence

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        previous = ""
        for sequence, row in enumerate(rows, 1):
            claimed = row.get("event_hash")
            body = {key: value for key, value in row.items() if key != "event_hash"}
            canonical = json.dumps(body, separators=(",", ":"), sort_keys=True, default=str)
            if (
                row.get("sequence") != sequence
                or row.get("previous_hash") != previous
                or claimed != hashlib.sha256(canonical.encode()).hexdigest()
            ):
                raise ValueError("postback journal integrity verification failed")
            previous = str(claimed)
        return rows


def create_app(
    config: ArrowConfig | None = None,
    *,
    exchange: TokenExchange | None = None,
    journal: PostbackJournal | None = None,
    expected_user_id: str | None = None,
) -> FastAPI:
    resolved = config or ArrowConfig.from_env()
    token_store = RuntimeTokenStore()
    pinned_user_id = expected_user_id if expected_user_id is not None else os.getenv("ARROW_EXPECTED_USER_ID", "")
    if not pinned_user_id.strip():
        raise ArrowConfigurationError("ARROW_EXPECTED_USER_ID is required")
    coordinator = AuthCallbackCoordinator(
        resolved,
        exchange or ArrowTokenExchangeClient(resolved),
        token_store,
        expected_user_id=pinned_user_id,
    )
    postbacks = journal or PostbackJournal(
        os.getenv("ARROW_POSTBACK_JOURNAL", "/var/lib/arrow-callback/postbacks.jsonl")
    )
    app = FastAPI(title="Arrow callback boundary", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["arrow.alphabullacademy.com", "localhost", "testserver"])
    app.state.token_store = token_store

    @app.get("/healthz")
    async def health() -> dict[str, object]:
        return {"status": "ok", "routing_enabled": False, "authenticated": bool(token_store.access_token)}

    @app.get("/auth/callback", response_class=HTMLResponse)
    async def auth_callback(request: Request) -> HTMLResponse:
        request_token = request.query_params.get("request-token", "")
        checksum = request.query_params.get("checksum", "")
        try:
            await coordinator.accept(request_token, checksum)
        except ArrowAuthenticationError as exc:
            raise HTTPException(status_code=400, detail="Arrow authentication callback rejected") from exc
        return HTMLResponse(
            "<h1>Arrow authentication completed</h1>"
            "<p>The execution service verified the callback. You may close this window.</p>"
        )

    @app.post("/order/postback", status_code=202)
    async def order_postback(request: Request) -> dict[str, object]:
        length = request.headers.get("content-length", "0")
        if length.isdigit() and int(length) > MAX_POSTBACK_BYTES:
            raise HTTPException(status_code=413, detail="postback is too large")
        body = await request.body()
        if len(body) > MAX_POSTBACK_BYTES:
            raise HTTPException(status_code=413, detail="postback is too large")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="postback must be JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="postback must be a JSON object")
        source = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
        sequence = await asyncio.to_thread(postbacks.append, payload, source=source)
        return {"status": "accepted", "sequence": sequence, "routing_enabled": False}

    return app
