from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from .models import (
    BrokerOrder,
    FillEvent,
    IntentRole,
    Mode,
    OrderIntent,
    OrderType,
    Phase,
    Side,
    StrategyProfile,
    StrategyState,
    canonical_json,
)

SCHEMA_VERSION = 1


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS profiles (
                    profile_id TEXT PRIMARY KEY,
                    account_alias TEXT NOT NULL,
                    ruleset_version TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    division_count INTEGER NOT NULL,
                    capital TEXT NOT NULL,
                    status TEXT NOT NULL,
                    effective_from TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_states (
                    profile_id TEXT PRIMARY KEY REFERENCES profiles(profile_id),
                    payload TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    input_hash TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(input_hash, phase)
                );
                CREATE TABLE IF NOT EXISTS order_intents (
                    intent_id TEXT PRIMARY KEY,
                    input_hash TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    side TEXT NOT NULL,
                    order_type TEXT NOT NULL,
                    role TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    limit_price TEXT,
                    budget TEXT NOT NULL,
                    planned_t_effect TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_orders (
                    broker_order_no TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL UNIQUE REFERENCES order_intents(intent_id),
                    status TEXT NOT NULL,
                    requested_qty INTEGER NOT NULL,
                    filled_qty INTEGER NOT NULL,
                    remaining_qty INTEGER NOT NULL,
                    submitted_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    raw_response_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fills (
                    broker_order_no TEXT NOT NULL,
                    fill_id TEXT NOT NULL,
                    intent_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    applied INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(broker_order_no, fill_id)
                );
                CREATE TABLE IF NOT EXISTS capabilities (
                    name TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    evidence TEXT NOT NULL,
                    checked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS live_approvals (
                    account_alias TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    approved_at TEXT NOT NULL,
                    PRIMARY KEY(account_alias, session_date)
                );
                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scheduler_runs (
                    run_id TEXT PRIMARY KEY,
                    session_date TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS advisory_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'rejected_by_default',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            db.execute(
                "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, _now()),
            )

    def create_profile(self, profile: StrategyProfile) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO profiles(profile_id, account_alias, ruleset_version, symbol, division_count, capital, status, effective_from)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile.profile_id,
                    profile.account_alias,
                    profile.ruleset_version,
                    profile.symbol,
                    profile.division_count,
                    str(profile.capital),
                    profile.status,
                    profile.effective_from.isoformat(),
                ),
            )
            initial = StrategyState(
                profile_id=profile.profile_id,
                cycle_id=f"{profile.profile_id}-cycle-1",
                session_date=profile.effective_from,
                cash=profile.capital,
            )
            self._save_state(db, initial, expected_version=None)

    def get_profile(self, profile_id: str) -> StrategyProfile:
        with self.connect() as db:
            row = db.execute("SELECT * FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
        if row is None:
            raise KeyError(f"profile not found: {profile_id}")
        return StrategyProfile(
            profile_id=row["profile_id"],
            account_alias=row["account_alias"],
            ruleset_version=row["ruleset_version"],
            symbol=row["symbol"],
            division_count=row["division_count"],
            capital=Decimal(row["capital"]),
            status=row["status"],
            effective_from=date.fromisoformat(row["effective_from"]),
        )

    def list_profiles(self) -> list[StrategyProfile]:
        with self.connect() as db:
            ids = [row[0] for row in db.execute("SELECT profile_id FROM profiles ORDER BY profile_id")]
        return [self.get_profile(profile_id) for profile_id in ids]

    def get_state(self, profile_id: str) -> StrategyState:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM strategy_states WHERE profile_id=?", (profile_id,)).fetchone()
        if row is None:
            raise KeyError(f"state not found: {profile_id}")
        return _state_from_json(row["payload"])

    def save_state(self, state: StrategyState, expected_version: int) -> None:
        with self.connect() as db:
            self._save_state(db, state, expected_version)

    def _save_state(self, db: sqlite3.Connection, state: StrategyState, expected_version: int | None) -> None:
        payload = canonical_json(state)
        if expected_version is None:
            db.execute(
                "INSERT INTO strategy_states(profile_id, payload, version, updated_at) VALUES (?, ?, ?, ?)",
                (state.profile_id, payload, state.version, _now()),
            )
            return
        cursor = db.execute(
            "UPDATE strategy_states SET payload=?, version=?, updated_at=? WHERE profile_id=? AND version=?",
            (payload, state.version, _now(), state.profile_id, expected_version),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("optimistic lock failed for strategy state")

    def record_decision(self, profile_id: str, session_date: date, phase: Phase, input_hash: str, intents: list[OrderIntent]) -> int:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO decisions(input_hash, phase, profile_id, session_date, created_at) VALUES (?, ?, ?, ?, ?)",
                (input_hash, phase.value, profile_id, session_date.isoformat(), _now()),
            )
            inserted = 0
            for intent in intents:
                cursor = db.execute(
                    """INSERT OR IGNORE INTO order_intents(
                        intent_id,input_hash,profile_id,session_date,phase,side,order_type,role,quantity,limit_price,budget,
                        planned_t_effect,reason_code,payload,status,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'PENDING', ?)""",
                    (
                        intent.intent_id,
                        intent.input_hash,
                        intent.profile_id,
                        intent.session_date.isoformat(),
                        intent.phase.value,
                        intent.side.value,
                        intent.order_type.value,
                        intent.role.value,
                        intent.quantity,
                        str(intent.limit_price) if intent.limit_price is not None else None,
                        str(intent.budget),
                        str(intent.planned_t_effect),
                        intent.reason_code,
                        canonical_json(intent),
                        _now(),
                    ),
                )
                inserted += cursor.rowcount
            return inserted

    def pending_intents(self, profile_id: str, session_date: date, phase: Phase) -> list[OrderIntent]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM order_intents WHERE profile_id=? AND session_date=? AND phase=? AND status='PENDING' ORDER BY side DESC, role",
                (profile_id, session_date.isoformat(), phase.value),
            ).fetchall()
        return [_intent_from_json(row["payload"]) for row in rows]

    def record_broker_order(self, order: BrokerOrder) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO broker_orders(broker_order_no,intent_id,status,requested_qty,filled_qty,remaining_qty,submitted_at,last_checked_at,raw_response_hash)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    order.broker_order_no,
                    order.intent_id,
                    order.status,
                    order.requested_qty,
                    order.filled_qty,
                    order.remaining_qty,
                    order.submitted_at.isoformat(),
                    order.last_checked_at.isoformat() if order.last_checked_at else None,
                    order.raw_response_hash,
                ),
            )
            db.execute("UPDATE order_intents SET status='SUBMITTED' WHERE intent_id=?", (order.intent_id,))

    def mark_intent_unknown(self, intent_id: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE order_intents SET status='UNKNOWN' WHERE intent_id=?", (intent_id,))

    def has_order_for_intent(self, intent_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM broker_orders WHERE intent_id=?", (intent_id,)).fetchone() is not None

    def get_intent(self, intent_id: str) -> OrderIntent:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM order_intents WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None:
            raise KeyError(f"intent not found: {intent_id}")
        return _intent_from_json(row["payload"])

    def get_order(self, broker_order_no: str) -> sqlite3.Row:
        with self.connect() as db:
            row = db.execute("SELECT * FROM broker_orders WHERE broker_order_no=?", (broker_order_no,)).fetchone()
        if row is None:
            raise KeyError(f"order not found: {broker_order_no}")
        return row

    def update_order_status(self, broker_order_no: str, status: str, filled_qty: int, remaining_qty: int) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE broker_orders SET status=?,filled_qty=?,remaining_qty=?,last_checked_at=? WHERE broker_order_no=?",
                (status, filled_qty, remaining_qty, _now(), broker_order_no),
            )

    def list_orders(self) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute("SELECT * FROM broker_orders ORDER BY submitted_at DESC").fetchall()

    def daily_submitted_notional(self, session_date: date) -> Decimal:
        with self.connect() as db:
            rows = db.execute(
                """SELECT i.quantity, i.limit_price
                   FROM order_intents i JOIN broker_orders b ON b.intent_id=i.intent_id
                   WHERE i.session_date=?""",
                (session_date.isoformat(),),
            ).fetchall()
        return sum((Decimal(row["limit_price"]) * row["quantity"] for row in rows if row["limit_price"] is not None), Decimal(0))

    def add_fill(self, fill: FillEvent) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO fills(broker_order_no,fill_id,intent_id,payload) VALUES (?,?,?,?)",
                (fill.broker_order_no, fill.fill_id, fill.intent_id, canonical_json(fill)),
            )
            return cursor.rowcount == 1

    def pending_fills(self, profile_id: str) -> list[FillEvent]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT f.payload FROM fills f JOIN order_intents i ON i.intent_id=f.intent_id
                   WHERE i.profile_id=? AND f.applied=0 ORDER BY json_extract(f.payload, '$.filled_at'), f.fill_id""",
                (profile_id,),
            ).fetchall()
        return [_fill_from_json(row["payload"]) for row in rows]

    def save_reconciled_state(self, state: StrategyState, expected_version: int, fills: list[FillEvent]) -> None:
        with self.connect() as db:
            self._save_state(db, state, expected_version)
            for fill in fills:
                db.execute("UPDATE fills SET applied=1 WHERE broker_order_no=? AND fill_id=?", (fill.broker_order_no, fill.fill_id))

    def set_capability(self, name: str, status: str, evidence: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO capabilities(name,status,evidence,checked_at) VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET status=excluded.status,evidence=excluded.evidence,checked_at=excluded.checked_at",
                (name, status, evidence, _now()),
            )

    def capability(self, name: str) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT status FROM capabilities WHERE name=?", (name,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, value, _now()),
            )

    def setting(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def approve_live(self, account_alias: str, session_date: date) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO live_approvals(account_alias,session_date,approved_at) VALUES (?,?,?)",
                (account_alias, session_date.isoformat(), _now()),
            )

    def is_live_approved(self, account_alias: str, session_date: date) -> bool:
        with self.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM live_approvals WHERE account_alias=? AND session_date=?",
                    (account_alias, session_date.isoformat()),
                ).fetchone()
                is not None
            )

    def audit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(event_type,payload,created_at) VALUES (?,?,?)", (event_type, canonical_json(payload), _now()))

    def claim_scheduler_run(self, run_id: str, session_date: date, phase: Phase) -> bool:
        with self.connect() as db:
            row = db.execute("SELECT status FROM scheduler_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO scheduler_runs(run_id,session_date,phase,status,created_at) VALUES (?,?,?,?,?)",
                    (run_id, session_date.isoformat(), phase.value, "CLAIMED", _now()),
                )
                return True
            if row["status"] == "FAILED":
                db.execute("UPDATE scheduler_runs SET status='CLAIMED',created_at=? WHERE run_id=?", (_now(), run_id))
                return True
            return False

    def finish_scheduler_run(self, run_id: str, status: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE scheduler_runs SET status=? WHERE run_id=?", (status, run_id))

    def claim_oauth_request(self, account_alias: str, now: datetime, minimum_interval_seconds: int) -> bool:
        key = f"oauth_last_request_at:{account_alias}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row is not None:
                previous = datetime.fromisoformat(row["value"])
                if (now - previous).total_seconds() < minimum_interval_seconds:
                    return False
            db.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, now.isoformat(), _now()),
            )
            return True

    def reserve_api_slot(self, account_alias: str, now: datetime, minimum_interval_seconds: float) -> float:
        if minimum_interval_seconds <= 0:
            raise ValueError("minimum_interval_seconds must be positive")
        key = f"api_next_request_at:{account_alias}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            scheduled = now
            if row is not None:
                reserved = datetime.fromisoformat(row["value"])
                if reserved > scheduled:
                    scheduled = reserved
            next_slot = scheduled + timedelta(seconds=minimum_interval_seconds)
            db.execute(
                "INSERT INTO settings(key,value,updated_at) VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, next_slot.isoformat(), _now()),
            )
            return max(0.0, (scheduled - now).total_seconds())

    def backup(self, target: str | Path) -> Path:
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as dest:
            source.backup(dest)
        return destination

    def restore(self, source: str | Path) -> None:
        candidate = Path(source)
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        with sqlite3.connect(candidate) as check:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise ValueError(f"invalid backup: {result}")
        with sqlite3.connect(candidate) as source, sqlite3.connect(self.path) as destination:
            source.backup(destination)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _state_from_json(payload: str) -> StrategyState:
    data = json.loads(payload)
    return StrategyState(
        profile_id=data["profile_id"],
        cycle_id=data["cycle_id"],
        session_date=date.fromisoformat(data["session_date"]),
        cash=Decimal(data["cash"]),
        quantity=data["quantity"],
        cost_basis=Decimal(data["cost_basis"]),
        t=Decimal(data["t"]),
        mode=Mode(data["mode"]),
        reverse_cash_pool=Decimal(data["reverse_cash_pool"]),
        reverse_cash_used=Decimal(data["reverse_cash_used"]),
        reverse_days=data["reverse_days"],
        last_5_closes=tuple(Decimal(value) for value in data["last_5_closes"]),
        version=data["version"],
        reconciliation_required=data["reconciliation_required"],
    )


def _intent_from_json(payload: str) -> OrderIntent:
    data = json.loads(payload)
    return OrderIntent(
        intent_id=data["intent_id"],
        input_hash=data["input_hash"],
        cycle_id=data["cycle_id"],
        profile_id=data["profile_id"],
        strategy_version=data["strategy_version"],
        session_date=date.fromisoformat(data["session_date"]),
        phase=Phase(data["phase"]),
        side=Side(data["side"]),
        order_type=OrderType(data["order_type"]),
        role=IntentRole(data["role"]),
        quantity=data["quantity"],
        limit_price=Decimal(data["limit_price"]) if data["limit_price"] is not None else None,
        budget=Decimal(data["budget"]),
        planned_t_effect=Decimal(data["planned_t_effect"]),
        reason_code=data["reason_code"],
    )


def _fill_from_json(payload: str) -> FillEvent:
    data = json.loads(payload)
    return FillEvent(
        broker_order_no=data["broker_order_no"],
        fill_id=data["fill_id"],
        intent_id=data["intent_id"],
        side=Side(data["side"]),
        role=IntentRole(data["role"]),
        requested_qty=data["requested_qty"],
        filled_qty=data["filled_qty"],
        fill_price=Decimal(data["fill_price"]),
        filled_at=datetime.fromisoformat(data["filled_at"]),
    )
