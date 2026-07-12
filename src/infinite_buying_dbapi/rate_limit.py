from __future__ import annotations

import time
from datetime import datetime, timezone

from .store import StateStore


class DbSecRateLimiter:
    def __init__(self, store: StateStore, account_alias: str, requests_per_second: float):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self.store = store
        self.account_alias = account_alias
        self.minimum_interval = 1.0 / requests_per_second

    def wait(self) -> None:
        delay = self.store.reserve_api_slot(self.account_alias, datetime.now(timezone.utc), self.minimum_interval)
        if delay > 0:
            time.sleep(delay)
