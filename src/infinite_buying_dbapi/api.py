from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import canonical_json

API_SCHEMA_VERSION = "2.0"


def envelope(
    data: Any = None,
    *,
    ok: bool = True,
    warnings: list[dict[str, Any]] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": API_SCHEMA_VERSION,
        "ok": ok,
        "data": data,
        "warnings": warnings or [],
        "errors": errors or [],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def envelope_json(*args: Any, **kwargs: Any) -> str:
    return canonical_json(envelope(*args, **kwargs))
