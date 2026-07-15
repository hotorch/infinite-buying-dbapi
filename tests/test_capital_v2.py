from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from infinite_buying_dbapi.capital import CapitalError, apply_allocation, available_settled_usd, normalize_capital_rows, reserved_buy_notional
from infinite_buying_dbapi.models import StrategyProfile
from infinite_buying_dbapi.store import StateStore


def _store(tmp_path) -> StateStore:
    store = StateStore(tmp_path / "state.sqlite3")
    store.create_profile(StrategyProfile("tqqq", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2)))
    store.create_profile(StrategyProfile("soxl", "SOXL", 40, Decimal("8000"), effective_from=date(2026, 1, 2)))
    return store


def test_normalize_capital_rows_classifies_and_rejects_unknown() -> None:
    rows = [
        {"event_code": "DEPOSIT", "occurred_at": "2026-01-05T01:00:00+00:00", "amount": "1000", "currency": "USD", "settled": True, "transaction_id": "1"},
        {"event_code": "WITHDRAWAL", "occurred_at": "2026-01-06T01:00:00+00:00", "amount": "20", "currency": "USD", "settled": True, "transaction_id": "2"},
    ]
    events = normalize_capital_rows("default", rows)
    assert events[0]["event_type"] == "external_deposit"
    assert events[1]["amount"] == "-20"
    with pytest.raises(CapitalError, match="UNSUPPORTED_CAPITAL_EVENT"):
        normalize_capital_rows("default", [{**rows[0], "event_code": "MYSTERY"}])
    with pytest.raises(CapitalError, match="UNSUPPORTED_CAPITAL_CURRENCY"):
        normalize_capital_rows("default", [{**rows[0], "currency": "EUR"}])


def test_capital_can_split_one_settled_event_between_profiles(tmp_path) -> None:
    store = _store(tmp_path)
    event = normalize_capital_rows(
        "default",
        [{"event_code": "DEPOSIT", "occurred_at": "2026-01-05T01:00:00+00:00", "amount": "1000", "currency": "USD", "settled": True, "transaction_id": "deposit-1"}],
    )[0]
    assert store.record_capital_event(event)
    assert not store.record_capital_event(event)
    assert available_settled_usd(store, "default") == Decimal("1000")
    assert reserved_buy_notional(store, "tqqq") == 0

    current = apply_allocation(store, "tqqq", Decimal("400"), "current_cycle")
    waiting = apply_allocation(store, "soxl", Decimal("600"), "next_cycle")

    assert current["amount"] == "400" and waiting["timing"] == "next_cycle"
    assert store.get_state("tqqq").cash == Decimal("10400")
    assert store.get_state("soxl").cash == Decimal("8000")
    assert available_settled_usd(store, "default") == 0
    assert store.activate_next_cycle_capital("soxl") == Decimal("600")
    assert store.get_profile("soxl").capital == Decimal("8600")
    assert store.activate_next_cycle_capital("soxl") == 0


def test_capital_allocation_fails_closed(tmp_path) -> None:
    store = _store(tmp_path)
    with pytest.raises(CapitalError, match="EXCEEDS_SETTLED"):
        apply_allocation(store, "tqqq", Decimal("1"), "current_cycle")
    with pytest.raises(CapitalError, match="timing"):
        apply_allocation(store, "tqqq", Decimal("1"), "now")
    with pytest.raises(CapitalError, match="positive"):
        apply_allocation(store, "tqqq", Decimal("0"), "next_cycle")


def test_unexpected_withdrawal_locks_account_profiles(tmp_path) -> None:
    store = _store(tmp_path)
    event = normalize_capital_rows(
        "default",
        [{"event_code": "WITHDRAWAL", "occurred_at": "2026-01-05T01:00:00+00:00", "amount": "100", "currency": "USD", "settled": True, "transaction_id": "withdraw-1"}],
    )[0]
    assert store.record_capital_event(event)
    assert {store.get_profile("tqqq").status, store.get_profile("soxl").status} == {"LOCKED"}
    assert store.get_state("tqqq").reconciliation_required
