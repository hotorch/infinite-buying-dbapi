from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from infinite_buying_dbapi.broker import PaperBroker
from infinite_buying_dbapi.execution import ExecutionLimits, PreflightError, assert_live_gates, execute_intents, preflight_intents
from infinite_buying_dbapi.models import Environment, MarketSnapshot, Phase, StrategyProfile
from infinite_buying_dbapi.store import StateStore
from infinite_buying_dbapi.strategy import generate_intents


@pytest.fixture()
def setup_store(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p1", "TQQQ", 40, Decimal("10000"), effective_from=date(2026, 1, 2))
    store.create_profile(profile)
    return store, profile


def test_decision_and_submission_are_idempotent(setup_store) -> None:
    store, profile = setup_store
    state = store.get_state("p1")
    snapshot = MarketSnapshot(date(2026, 1, 5), Decimal("100"))
    _, intents = generate_intents(profile, state, snapshot, Phase.BUY)
    assert store.record_decision("p1", snapshot.session_date, Phase.BUY, intents[0].input_hash, intents) == 1
    assert store.record_decision("p1", snapshot.session_date, Phase.BUY, intents[0].input_hash, intents) == 0
    limits = ExecutionLimits(Decimal("10000"), Decimal("20000"))
    first = execute_intents(store, PaperBroker(), profile, state, intents, Environment.PAPER, limits)
    second = execute_intents(store, PaperBroker(), profile, state, intents, Environment.PAPER, limits)
    assert len(first) == 1
    assert second == []


def test_live_fails_closed_until_every_gate_passes(setup_store) -> None:
    store, profile = setup_store
    with pytest.raises(PreflightError) as exc:
        assert_live_gates(store, profile, store.get_state("p1"), date(2026, 1, 5))
    assert "OPPOSING_LOC_NOT_VERIFIED" in str(exc.value)
    for key in ("live_enabled", "legal_review_ack", "risk_disclosure_ack"):
        store.set_setting(key, "true")
    store.set_setting("emergency_stop", "false")
    store.set_capability("supports_opposing_loc", "확인됨", "testbed evidence")
    store.set_capability("oauth_client_credentials", "확인됨", "official OAuth workbook")
    store.set_capability("rate_limits", "확인됨", "official TR evidence")
    store.approve_live(profile.account_alias, date(2026, 1, 5))
    assert_live_gates(store, profile, store.get_state("p1"), date(2026, 1, 5))


def test_30_division_is_never_live_eligible(tmp_path) -> None:
    store = StateStore(tmp_path / "state.sqlite3")
    profile = StrategyProfile("p30", "TQQQ", 30, Decimal("10000"))
    store.create_profile(profile)
    with pytest.raises(PreflightError, match="PROFILE_NOT_LIVE_ELIGIBLE"):
        assert_live_gates(store, profile, store.get_state("p30"), date.today())


def test_preflight_blocks_oversell_and_notional(setup_store) -> None:
    store, profile = setup_store
    state = store.get_state("p1")
    _, intent = generate_intents(profile, state, MarketSnapshot(date(2026, 1, 5), Decimal("100")), Phase.BUY)
    with pytest.raises(PreflightError, match="ORDER_NOTIONAL"):
        preflight_intents(intent, state, ExecutionLimits(Decimal("10"), Decimal("20")))


def test_optimistic_lock(setup_store) -> None:
    store, _ = setup_store
    original = store.get_state("p1")
    changed = original.evolved(cash=Decimal("9999"))
    store.save_state(changed, original.version)
    with pytest.raises(RuntimeError, match="optimistic lock"):
        store.save_state(original.evolved(cash=Decimal("9998")), original.version)


def test_backup_restore_settings_and_scheduler_claim(setup_store, tmp_path) -> None:
    store, _ = setup_store
    store.set_setting("sample", "one")
    backup = store.backup(tmp_path / "backup.sqlite3")
    store.set_setting("sample", "two")
    store.restore(backup)
    assert StateStore(store.path).setting("sample") == "one"
    assert store.claim_scheduler_run("p1:2026-01-05:buy", date(2026, 1, 5), Phase.BUY)
    assert not store.claim_scheduler_run("p1:2026-01-05:buy", date(2026, 1, 5), Phase.BUY)
    store.finish_scheduler_run("p1:2026-01-05:buy", "FAILED")
    assert store.claim_scheduler_run("p1:2026-01-05:buy", date(2026, 1, 5), Phase.BUY)
    store.finish_scheduler_run("p1:2026-01-05:buy", "COMPLETED")


def test_cross_process_api_slot_reservation(setup_store) -> None:
    store, _ = setup_store
    now = datetime(2026, 1, 5, tzinfo=timezone.utc)
    assert store.reserve_api_slot("default", now, 0.5) == 0
    assert store.reserve_api_slot("default", now, 0.5) == 0.5
