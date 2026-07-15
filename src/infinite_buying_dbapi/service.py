from __future__ import annotations

from datetime import date
from decimal import Decimal

from .models import MarketSnapshot, OrderIntent, Phase, stable_hash
from .store import StateStore
from .strategy import generate_intents


def preview_phase(
    store: StateStore,
    profile_id: str,
    session_date: date,
    previous_close: Decimal,
    phase: Phase,
    completed_closes: tuple[Decimal, ...] = (),
) -> list[OrderIntent]:
    """Calculate a phase without mutating strategy state, decisions, or outbox."""
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    snapshot = MarketSnapshot(session_date=session_date, previous_close=previous_close, completed_closes=completed_closes)
    _, intents = generate_intents(profile, state, snapshot, phase)
    return intents


def plan_phase(
    store: StateStore,
    profile_id: str,
    session_date: date,
    previous_close: Decimal,
    phase: Phase,
    completed_closes: tuple[Decimal, ...] = (),
) -> tuple[list[OrderIntent], int]:
    profile = store.get_profile(profile_id)
    state = store.get_state(profile_id)
    snapshot = MarketSnapshot(session_date=session_date, previous_close=previous_close, completed_closes=completed_closes)
    prepared, intents = generate_intents(profile, state, snapshot, phase)
    if prepared != state:
        store.save_state(prepared, expected_version=state.version)
    input_hash = (
        intents[0].input_hash
        if intents
        else stable_hash({"profile_id": profile_id, "session_date": session_date, "phase": phase, "state_version": prepared.version})
    )
    inserted = store.record_decision(profile_id, session_date, phase, input_hash, intents)
    return intents, inserted
