from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
    except (IndexError, KeyError, TypeError, ValueError, binascii.Error, json.JSONDecodeError):
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


@dataclass
class CallbackTokenProvider:
    callback: Callable[[], Awaitable[str]]

    async def get_token(self) -> str:
        token = await self.callback()
        if not token:
            raise ArrowAuthenticationError("token provider returned an empty token")
        return token


class ArrowAuthManager:
    def __init__(self, config: ArrowConfig, provider: TokenProvider | None = None) -> None:
        self.config = config
        self.provider = provider or StaticTokenProvider(config.access_token)
        self.state = AuthState.UNCONFIGURED
        self.token = ""  # nosec B105 - empty value clears in-memory credential state
        self.expiration: datetime | None = None
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
            self.expiration = expiry
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

    async def ensure_authenticated(self, *, minimum_validity_seconds: float = 30.0) -> str:
        if minimum_validity_seconds < 0:
            raise ValueError("minimum token validity cannot be negative")
        refresh_at = datetime.now(UTC) + timedelta(seconds=minimum_validity_seconds)
        if (
            self.state != AuthState.AUTHENTICATED
            or not self.token
            or (self.expiration is not None and self.expiration <= refresh_at)
        ):
            return await self.reauthenticate()
        return self.token

    def invalidate(self) -> None:
        self.token = ""  # nosec B105 - empty value clears in-memory credential state
        self.expiration = None
        self.state = AuthState.EXPIRED
