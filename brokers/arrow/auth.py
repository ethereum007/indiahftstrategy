from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from brokers.arrow.config import ArrowConfig
from brokers.arrow.errors import ArrowAuthenticationError


class AuthState(StrEnum):
    UNCONFIGURED = "UNCONFIGURED"
    CONFIGURED = "CONFIGURED"
    AUTHENTICATING = "AUTHENTICATING"
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


def request_checksum(app_id: str, request_token: str) -> str:
    return hashlib.sha256(f"{request_token}:{app_id}".encode()).hexdigest()


def token_exchange_checksum(app_id: str, app_secret: str, request_token: str) -> str:
    return hashlib.sha256(f"{app_id}:{app_secret}:{request_token}".encode()).hexdigest()


def jwt_expiration(token: str) -> datetime | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload))["exp"]
        return datetime.fromtimestamp(int(exp), tz=UTC)
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class TokenProvider(Protocol):
    async def get_token(self) -> str: ...


@dataclass
class StaticTokenProvider:
    token: str

    async def get_token(self) -> str:
        if not self.token:
            raise ArrowAuthenticationError("access token is empty")
        return self.token


class ArrowAuthManager:
    def __init__(self, config: ArrowConfig, provider: TokenProvider | None = None) -> None:
        self.config = config
        self.provider = provider or StaticTokenProvider(config.access_token)
        self.state = AuthState.UNCONFIGURED
        self.token = ""  # nosec B105 - empty value clears in-memory credential state
        self.on_reauthenticate: list[Callable[[], Awaitable[None]]] = []

    async def authenticate(self) -> str:
        try:
            self.config.validate()
            self.state = AuthState.CONFIGURED
            self.state = AuthState.AUTHENTICATING
            token = await self.provider.get_token()
            expiry = jwt_expiration(token)
            if expiry is not None and expiry <= datetime.now(UTC):
                self.state = AuthState.EXPIRED
                raise ArrowAuthenticationError("access token is expired")
            self.token = token
            self.state = AuthState.AUTHENTICATED
            return token
        except Exception:
            if self.state != AuthState.EXPIRED:
                self.state = AuthState.FAILED
            raise

    async def reauthenticate(self) -> str:
        token = await self.authenticate()
        for hook in self.on_reauthenticate:
            await hook()
        return token

    def invalidate(self) -> None:
        self.token = ""  # nosec B105 - empty value clears in-memory credential state
        self.state = AuthState.EXPIRED
