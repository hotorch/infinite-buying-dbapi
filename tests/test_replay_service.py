from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from infinite_buying_dbapi.models import Phase, StrategyProfile
from infinite_buying_dbapi.replay import replay_file
from infinite_buying_dbapi.service import plan_phase
from infinite_buying_dbapi.store import StateStore


def test_replay_uses_production_core(tmp_path) -> None:
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    source = tmp_path / "events.json"
    source.write_text(
        json.dumps(
            [
                {
                    "date": "2026-01-05",
                    "previous_close": "100",
                    "completed_closes": ["96", "97", "98", "99", "100"],
                    "fills": {"initial_buy": {"price": "120"}},
                }
            ]
        ),
        encoding="utf-8",
    )
    result = replay_file(profile, source)
    assert result["final_state"]["quantity"] == 2
    assert result["final_state"]["t"] == Decimal(1)
    assert result["decisions"]


def test_plan_phase_persists_intents_idempotently(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    store.create_profile(profile)
    first, inserted = plan_phase(store, "p1", date(2026, 1, 5), Decimal("100"), Phase.BUY)
    second, inserted_again = plan_phase(store, "p1", date(2026, 1, 5), Decimal("100"), Phase.BUY)
    assert first == second
    assert inserted == 1 and inserted_again == 0
