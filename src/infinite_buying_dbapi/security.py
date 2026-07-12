from __future__ import annotations

import re
from typing import Any

import keyring

SERVICE_NAME = "infinite-buying-dbapi"
SENSITIVE_KEYS = re.compile(r"token|secret|password|authorization|account(_?number)?", re.IGNORECASE)


def store_secret(account_alias: str, name: str, value: str) -> None:
    if not value:
        raise ValueError("secret cannot be empty")
    keyring.set_password(SERVICE_NAME, f"{account_alias}:{name}", value)


def get_secret(account_alias: str, name: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, f"{account_alias}:{name}")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***REDACTED***" if SENSITIVE_KEYS.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    return value


def mask_account(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return "*" * (len(value) - 4) + value[-4:]
