from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import Environment


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IB_", env_file=".env", extra="ignore")

    db_path: Path = Field(default_factory=lambda: user_data_path("InfiniteBuyingDBAPI", "Codex") / "state.sqlite3")
    account_alias: str = "default"
    environment: Environment = Environment.PREVIEW
    dbsec_base_url: str = "https://openapi.dbsec.co.kr:8443"
    max_order_notional_usd: Decimal = Decimal("1000")
    max_daily_notional_usd: Decimal = Decimal("2000")
    request_timeout_seconds: float = 10.0
    dbsec_requests_per_second: float | None = None
    dbsec_oauth_style: Literal["json", "form"] = "json"
