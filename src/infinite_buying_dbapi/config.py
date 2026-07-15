from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path
from typing import Literal

from platformdirs import user_data_path
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .models import AccountMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IB_", env_file=".env", extra="ignore")

    db_path: Path = Field(default_factory=lambda: user_data_path("InfiniteBuyingDBAPI", "Codex") / "state.sqlite3")
    account_alias: str = "default"
    dbsec_account_mode: AccountMode = AccountMode.REAL
    dbsec_base_url: str = "https://openapi.dbsec.co.kr:8443"
    max_order_notional_usd: Decimal | None = None
    max_daily_notional_usd: Decimal | None = None
    request_timeout_seconds: float = 10.0
    dbsec_requests_per_second: float | None = None
    dbsec_oauth_style: Literal["json", "form"] = "form"
    db_appkey: SecretStr | None = Field(default=None, validation_alias="DB_APPKEY")
    db_appsecret: SecretStr | None = Field(default=None, validation_alias="DB_APPSECRET")
    db_credential_env: str | None = Field(default=None, validation_alias="DB_ENV")
    db_expire_date: str | None = Field(default=None, validation_alias="DB_EXPIRE_DATE")

    @model_validator(mode="before")
    @classmethod
    def reject_v1_environment(cls, values: object) -> object:
        if os.getenv("IB_ENVIRONMENT") is not None:
            raise ValueError("IB_ENVIRONMENT was removed in 0.2.0; use IB_DBSEC_ACCOUNT_MODE=real")
        return values
