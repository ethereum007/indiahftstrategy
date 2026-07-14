from __future__ import annotations

import importlib
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlsplit


ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
ENTRYPOINT_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$"
)
SAFE_CODE_RE = re.compile(r"^[a-z0-9_]{0,64}$")
ALLOWED_SCHEMES = {
    "rest": {"https"},
    "websocket": {"wss"},
}


class ProviderConnectivityError(RuntimeError):
    """Raised when a connectivity probe contract cannot be constructed safely."""


@dataclass(frozen=True)
class ProviderConnectivityRequest:
    provider: str
    adapter: str
    transport: str
    endpoint: str
    market: str
    exchange: str
    session_id: str
    handoff_id: str
    plan_sha256: str
    credential_env_vars: tuple[str, ...]
    credential_env_presence: Mapping[str, bool]


@dataclass(frozen=True)
class ProviderConnectivityOutcome:
    connected: bool
    authenticated: bool
    market_data_readable: bool
    protocol: str = ""
    error_code: str = ""


ProviderConnectivityBackend = Callable[
    [ProviderConnectivityRequest],
    ProviderConnectivityOutcome,
]


@dataclass(frozen=True)
class ProviderConnectivityProbeResult:
    request: ProviderConnectivityRequest
    outcome: ProviderConnectivityOutcome
    backend_entrypoint: str
    probe_called: bool
    latency_ms: float

    @property
    def passed(self) -> bool:
        return bool(
            self.probe_called
            and self.outcome.connected
            and self.outcome.authenticated
            and self.outcome.market_data_readable
            and not self.outcome.error_code
        )


def execute_provider_connectivity_probe(
    *,
    provider: str,
    adapter: str,
    transport: str,
    endpoint: str,
    market: str,
    exchange: str,
    session_id: str,
    handoff_id: str,
    plan_sha256: str,
    credential_env_vars: tuple[str, ...],
    backend: ProviderConnectivityBackend,
    backend_entrypoint: str,
    environ: Mapping[str, str] | None = None,
) -> ProviderConnectivityProbeResult:
    environment = dict(os.environ if environ is None else environ)
    normalized_provider = _identity(provider)
    normalized_adapter = _identity(adapter)
    normalized_transport = _identity(transport)
    normalized_market = _identity(market)
    normalized_exchange = str(exchange).strip().upper()
    normalized_session = str(session_id).strip()
    normalized_handoff = str(handoff_id).strip()
    normalized_plan_sha = str(plan_sha256).strip().lower()
    normalized_endpoint = str(endpoint).strip()
    normalized_backend = str(backend_entrypoint).strip()
    env_vars = tuple(str(name).strip() for name in credential_env_vars)

    if not normalized_provider or not normalized_adapter:
        raise ProviderConnectivityError("provider and adapter are required")
    if normalized_transport not in ALLOWED_SCHEMES:
        raise ProviderConnectivityError("connectivity transport must be rest or websocket")
    endpoint_error = validate_connectivity_endpoint(
        normalized_endpoint,
        normalized_transport,
    )
    if endpoint_error:
        raise ProviderConnectivityError(endpoint_error)
    if not normalized_market or not normalized_exchange or not normalized_session:
        raise ProviderConnectivityError("market, exchange, and session identity are required")
    if not normalized_handoff or not _valid_sha256(normalized_plan_sha):
        raise ProviderConnectivityError("handoff identity is invalid")
    if not env_vars or len(set(env_vars)) != len(env_vars):
        raise ProviderConnectivityError("credential environment variables are required and unique")
    if any(not ENV_NAME_RE.fullmatch(name) for name in env_vars):
        raise ProviderConnectivityError("credential environment variables must be names")
    if not ENTRYPOINT_RE.fullmatch(normalized_backend):
        raise ProviderConnectivityError(
            "connectivity backend entrypoint must use module:function"
        )

    presence = {
        name: bool(str(environment.get(name, "")).strip())
        for name in env_vars
    }
    missing = [name for name, present in presence.items() if not present]
    if missing:
        raise ProviderConnectivityError(
            "required credential environment variables are missing: "
            + ", ".join(missing)
        )
    request = ProviderConnectivityRequest(
        provider=normalized_provider,
        adapter=normalized_adapter,
        transport=normalized_transport,
        endpoint=normalized_endpoint,
        market=normalized_market,
        exchange=normalized_exchange,
        session_id=normalized_session,
        handoff_id=normalized_handoff,
        plan_sha256=normalized_plan_sha,
        credential_env_vars=env_vars,
        credential_env_presence=presence,
    )
    started = time.perf_counter_ns()
    try:
        outcome = backend(request)
    except Exception as exc:  # pragma: no cover - provider behavior is external
        elapsed = _elapsed_ms(started)
        return ProviderConnectivityProbeResult(
            request=request,
            outcome=ProviderConnectivityOutcome(
                connected=False,
                authenticated=False,
                market_data_readable=False,
                error_code=_safe_code(f"backend_exception_{type(exc).__name__}"),
            ),
            backend_entrypoint=normalized_backend,
            probe_called=True,
            latency_ms=elapsed,
        )
    elapsed = _elapsed_ms(started)
    if not isinstance(outcome, ProviderConnectivityOutcome):
        outcome = ProviderConnectivityOutcome(
            connected=False,
            authenticated=False,
            market_data_readable=False,
            error_code="invalid_backend_outcome",
        )
    else:
        outcome = ProviderConnectivityOutcome(
            connected=outcome.connected is True,
            authenticated=outcome.authenticated is True,
            market_data_readable=outcome.market_data_readable is True,
            protocol=_safe_code(outcome.protocol),
            error_code=_safe_code(outcome.error_code),
        )
    return ProviderConnectivityProbeResult(
        request=request,
        outcome=outcome,
        backend_entrypoint=normalized_backend,
        probe_called=True,
        latency_ms=elapsed,
    )


def load_provider_connectivity_backend(
    entrypoint: str,
) -> ProviderConnectivityBackend:
    normalized = str(entrypoint).strip()
    if not ENTRYPOINT_RE.fullmatch(normalized):
        raise ProviderConnectivityError(
            "provider connectivity backend must use module:function"
        )
    module_name, separator, attribute = normalized.partition(":")
    if not separator or not module_name or not attribute:  # pragma: no cover
        raise ProviderConnectivityError("provider connectivity backend is invalid")
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise ProviderConnectivityError(
            f"provider connectivity backend module could not be imported ({type(exc).__name__})"
        ) from exc
    backend = getattr(module, attribute, None)
    if not callable(backend):
        raise ProviderConnectivityError(
            f"provider connectivity backend {normalized!r} is not callable"
        )
    return backend


def provider_connectivity_backend_env_var(provider: str) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(provider).strip().upper()).strip("_")
    return f"{normalized}_PROVIDER_CONNECTIVITY_BACKEND"


def resolve_provider_connectivity_backend_entrypoint(
    provider: str,
    explicit: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    environment = os.environ if environ is None else environ
    if str(explicit).strip():
        return str(explicit).strip()
    provider_key = provider_connectivity_backend_env_var(provider)
    return str(
        environment.get(provider_key)
        or environment.get("PROVIDER_CONNECTIVITY_BACKEND")
        or ""
    ).strip()


def validate_connectivity_endpoint(endpoint: str, transport: str) -> str:
    normalized_endpoint = str(endpoint).strip()
    normalized_transport = _identity(transport)
    try:
        parsed = urlsplit(normalized_endpoint)
    except ValueError:
        return "connectivity endpoint is invalid"
    if parsed.scheme.lower() not in ALLOWED_SCHEMES.get(normalized_transport, set()):
        return "connectivity endpoint must use a secure transport scheme"
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return "connectivity endpoint must not contain credentials"
    if parsed.query:
        return "connectivity endpoint must not contain query parameters"
    if parsed.fragment:
        return "connectivity endpoint must not contain a fragment"
    return ""


def _elapsed_ms(started_ns: int) -> float:
    return round(max(0, time.perf_counter_ns() - started_ns) / 1_000_000.0, 3)


def _safe_code(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9_]+", "_", str(value).strip().lower()).strip("_")
    normalized = normalized[:64]
    return normalized if SAFE_CODE_RE.fullmatch(normalized) else "invalid_code"


def _identity(value: object) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _valid_sha256(value: object) -> bool:
    text = str(value).strip().lower()
    return bool(
        len(text) == 64
        and all(character in "0123456789abcdef" for character in text)
    )
