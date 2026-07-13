from __future__ import annotations

from datetime import date
from decimal import Decimal

from infinite_buying_dbapi.models import BrokerOrder, MarketSnapshot, Phase, StrategyProfile
from infinite_buying_dbapi.reconciliation import reconcile_dbsec
from infinite_buying_dbapi.store import StateStore
from infinite_buying_dbapi.strategy import generate_intents


class FakeDbSec:
    def __init__(self, records, quantity):
        self.records = records
        self.quantity = quantity

    def transaction_history(self, start, end, symbol):
        return self.records

    def holding(self, symbol):
        return {"SymCode": symbol, "AstkExecBaseQty": str(self.quantity)} if self.quantity else None


def test_reconciliation_applies_fill_once_and_recovers(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    store.create_profile(profile)
    state = store.get_state("p1")
    _, intents = generate_intents(profile, state, MarketSnapshot(date(2026, 1, 5), Decimal("100")), Phase.BUY)
    intent = intents[0]
    store.record_decision("p1", date(2026, 1, 5), Phase.BUY, intent.input_hash, [intent])
    store.record_broker_order(BrokerOrder("101", intent.intent_id, "ACCEPTED", intent.quantity, remaining_qty=intent.quantity))
    row = {
        "OrdDt": "20260105",
        "OrdNo": 101,
        "ExecNo": 77,
        "AstkBnsTpCode": "2",
        "AstkExecQty": str(intent.quantity),
        "AstkExecPrc": "120",
        "AstkOrdRmqty": "0",
        "AstkRjtCode": "0",
        "AstkExecDttm": "20260105210000000",
    }
    broker = FakeDbSec([row], intent.quantity)
    first = reconcile_dbsec(store, broker, profile, date(2026, 1, 5))
    assert first.quantity == intent.quantity
    assert first.cash == Decimal("10000") - Decimal("120") * intent.quantity
    assert first.t == Decimal(1)
    second = reconcile_dbsec(store, broker, profile, date(2026, 1, 5))
    assert second == first


def test_reconciliation_flags_unknown_broker_order(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"))
    store.create_profile(profile)
    broker = FakeDbSec([{"OrdNo": 999, "AstkExecQty": "0", "AstkOrdRmqty": "1"}], 0)
    result = reconcile_dbsec(store, broker, profile, date.today())
    assert result.reconciliation_required


def test_reconciliation_fails_closed_when_empty_broker_differs_from_local(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"))
    store.create_profile(profile)
    state = store.get_state("p1")
    store.save_state(state.evolved(quantity=2, cost_basis=Decimal("200")), state.version)

    result = reconcile_dbsec(store, FakeDbSec([], 0), profile, date.today())

    assert result.reconciliation_required
    assert store.get_state("p1").reconciliation_required
