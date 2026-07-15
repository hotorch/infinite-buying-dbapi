from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from typer.testing import CliRunner

from infinite_buying_dbapi.broker import AmbiguousOrderError
from infinite_buying_dbapi.cli import app
from infinite_buying_dbapi.execution import ExecutionLimits, execute_intents
from infinite_buying_dbapi.models import Environment, FillEvent, MarketSnapshot, Phase, Side, StrategyProfile
from infinite_buying_dbapi.positions import apply_fills_with_cycles
from infinite_buying_dbapi.store import StateStore
from infinite_buying_dbapi.strategy import generate_intents
from infinite_buying_dbapi.weather import WeatherCandle, compute_weather_history


def test_preview_does_not_write_state_decision_or_outbox(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "state.sqlite3"
    monkeypatch.setenv("IB_DB_PATH", str(db_path))
    store = StateStore(db_path)
    store.create_profile(StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), status="OFF", effective_from=date(2026, 1, 2)))
    before = store.get_state("p1")

    result = CliRunner().invoke(app, ["preview", "p1", "--previous-close", "100", "--session-date", "2026-01-05"])

    assert result.exit_code == 0, result.output
    assert store.get_state("p1") == before
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM decisions").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM order_intents").fetchone()[0] == 0


def test_ambiguous_order_locks_profile_and_state(tmp_path) -> None:
    class AmbiguousBroker:
        def place_order(self, intent):
            raise AmbiguousOrderError("timeout")

        def cancel_order(self, broker_order_no, intent):
            raise AssertionError

    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    store.create_profile(profile)
    state = store.get_state("p1")
    _, intents = generate_intents(profile, state, MarketSnapshot(date(2026, 1, 5), Decimal("100")), Phase.BUY)
    store.record_decision("p1", date(2026, 1, 5), Phase.BUY, intents[0].input_hash, intents)

    with pytest.raises(AmbiguousOrderError):
        execute_intents(store, AmbiguousBroker(), profile, state, intents, Environment.PREVIEW, ExecutionLimits())

    assert store.get_profile("p1").status == "LOCKED"
    assert store.get_state("p1").reconciliation_required


def test_same_timestamp_sell_then_buy_opens_next_cycle(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    store.create_profile(profile)
    state = store.get_state("p1")
    _, buy_intents = generate_intents(profile, state, MarketSnapshot(date(2026, 1, 5), Decimal("100")), Phase.BUY)
    first_buy = buy_intents[0]
    at = datetime(2026, 1, 5, 21, tzinfo=timezone.utc)
    state = apply_fills_with_cycles(store, profile, state, [(first_buy, FillEvent("b1", "f1", first_buy.intent_id, Side.BUY, first_buy.role, first_buy.quantity, first_buy.quantity, Decimal("100"), at))])
    _, sell_intents = generate_intents(profile, state, MarketSnapshot(date(2026, 1, 6), Decimal("110")), Phase.SELL)
    target = next(item for item in sell_intents if item.quantity == state.quantity - max(1, state.quantity // 4))
    quarter = next(item for item in sell_intents if item is not target)
    sell_pairs = [
        (quarter, FillEvent("s1", "f2", quarter.intent_id, Side.SELL, quarter.role, quarter.quantity, quarter.quantity, Decimal("110"), at)),
        (target, FillEvent("s2", "f3", target.intent_id, Side.SELL, target.role, target.quantity, target.quantity, Decimal("110"), at)),
    ]
    flat = apply_fills_with_cycles(store, profile, state, sell_pairs)
    _, next_buys = generate_intents(profile, flat, MarketSnapshot(date(2026, 1, 6), Decimal("110")), Phase.BUY)
    reopened = apply_fills_with_cycles(store, profile, flat, [(next_buys[0], FillEvent("b2", "f4", next_buys[0].intent_id, Side.BUY, next_buys[0].role, next_buys[0].quantity, next_buys[0].quantity, Decimal("110"), at))])

    assert reopened.cycle_id.endswith("-2")
    assert [row["status"] for row in reversed(store.list_position_cycles("p1"))] == ["CLOSED", "OPEN"]


@pytest.mark.parametrize(("symbol", "signal"), [("TQQQ", "QQQ"), ("SOXL", "SMH")])
def test_weather_engine_supports_both_symbols(symbol: str, signal: str) -> None:
    start = date(2025, 1, 1)
    days = [start + timedelta(days=index) for index in range(340)]
    series = {
        symbol: [WeatherCandle(day, Decimal(100 + index), Decimal("10000000")) for index, day in enumerate(days)],
        signal: [WeatherCandle(day, Decimal(100 + index), Decimal("1000000")) for index, day in enumerate(days)],
        "SPY": [WeatherCandle(day, Decimal(100) + Decimal(index) / 2, Decimal("1000000")) for index, day in enumerate(days)],
    }
    history = compute_weather_history(symbol, series)
    assert history and history[-1].signal_symbol == signal
    assert history[-1].ruleset_version == "regime-weather-1"
