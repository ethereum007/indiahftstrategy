from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

SECRET_KEYS = {"token", "access_token", "app_secret", "authorization", "checksum"}


def redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): "***REDACTED***" if str(k).lower() in SECRET_KEYS else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def safe_log(logger: logging.Logger, message: str, context: Mapping[str, Any]) -> None:
    logger.info(message, extra={"arrow_context": redact(context)})
