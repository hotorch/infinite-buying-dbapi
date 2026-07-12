from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from .models import FillEvent, IntentRole, MarketSnapshot, Phase, Side, StrategyProfile, StrategyState, canonical_json
from .strategy import apply_fill, generate_intents


def replay_file(profile: StrategyProfile, source: str | Path) -> dict[str, Any]:
    rows = json.loads(Path(source).read_text(encoding="utf-8"))
    state = StrategyState(profile_id=profile.profile_id, cycle_id=f"{profile.profile_id}-replay", session_date=profile.effective_from, cash=profile.capital)
    decisions: list[dict[str, Any]] = []
    for row in rows:
        snapshot = MarketSnapshot(
            session_date=date.fromisoformat(row["date"]),
            previous_close=Decimal(str(row["previous_close"])),
            completed_closes=tuple(Decimal(str(value)) for value in row.get("completed_closes", [])),
        )
        for phase in (Phase.SELL, Phase.BUY):
            state, intents = generate_intents(profile, state, snapshot, phase)
            decisions.extend(asdict(intent) for intent in intents)
            fills = row.get("fills", {})
            for intent in intents:
                fill_spec = fills.get(intent.role.value)
                if not fill_spec:
                    continue
                fill = FillEvent(
                    broker_order_no=f"REPLAY-{len(decisions)}",
                    fill_id=f"{snapshot.session_date}-{intent.role.value}",
                    intent_id=intent.intent_id,
                    side=Side(intent.side),
                    role=IntentRole(intent.role),
                    requested_qty=intent.quantity,
                    filled_qty=int(fill_spec.get("quantity", intent.quantity)),
                    fill_price=Decimal(str(fill_spec["price"])),
                    filled_at=datetime.fromisoformat(fill_spec["filled_at"])
                    if fill_spec.get("filled_at")
                    else datetime.combine(snapshot.session_date, datetime.min.time(), tzinfo=timezone.utc),
                )
                state = apply_fill(profile, state, intent, fill)
    return {"profile": profile.profile_id, "final_state": asdict(state), "decisions": decisions, "digest": canonical_json(state)}
