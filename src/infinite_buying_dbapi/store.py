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
    WeatherSnapshot,
    canonical_json,
    stable_hash,
)

SCHEMA_VERSION = 2


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
                CREATE TABLE IF NOT EXISTS reconciliation_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    profile_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    details TEXT NOT NULL,
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
                (1, _now()),
            )
            self._migrate_v2(db)

    def _migrate_v2(self, db: sqlite3.Connection) -> None:
        if db.execute("SELECT 1 FROM schema_migrations WHERE version=2").fetchone():
            db.execute(
                """CREATE TABLE IF NOT EXISTS capital_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,event_key TEXT NOT NULL,profile_id TEXT NOT NULL,amount TEXT NOT NULL,
                    timing TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL
                )"""
            )
            db.execute("UPDATE profiles SET status='OFF' WHERE lower(status)='active'")
            db.execute("DROP TABLE IF EXISTS live_approvals")
            db.execute("DROP TABLE IF EXISTS scheduler_runs")
            return
        # A broker order number is only unique inside an account and order day.
        db.executescript(
            """
            CREATE TABLE broker_orders_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_alias TEXT NOT NULL,
                order_date TEXT NOT NULL,
                broker_order_no TEXT NOT NULL,
                intent_id TEXT NOT NULL UNIQUE REFERENCES order_intents(intent_id),
                status TEXT NOT NULL,
                requested_qty INTEGER NOT NULL,
                filled_qty INTEGER NOT NULL,
                remaining_qty INTEGER NOT NULL,
                submitted_at TEXT NOT NULL,
                last_checked_at TEXT,
                raw_response_hash TEXT NOT NULL,
                UNIQUE(account_alias, order_date, broker_order_no)
            );
            INSERT INTO broker_orders_v2(
                account_alias,order_date,broker_order_no,intent_id,status,requested_qty,filled_qty,remaining_qty,submitted_at,last_checked_at,raw_response_hash
            )
            SELECT COALESCE((SELECT p.account_alias FROM order_intents i JOIN profiles p ON p.profile_id=i.profile_id WHERE i.intent_id=b.intent_id),'default'),
                   COALESCE((SELECT i.session_date FROM order_intents i WHERE i.intent_id=b.intent_id),substr(b.submitted_at,1,10)),
                   b.broker_order_no,b.intent_id,b.status,b.requested_qty,b.filled_qty,b.remaining_qty,b.submitted_at,b.last_checked_at,b.raw_response_hash
            FROM broker_orders b;
            DROP TABLE broker_orders;
            ALTER TABLE broker_orders_v2 RENAME TO broker_orders;

            CREATE TABLE fills_v2 (
                account_alias TEXT NOT NULL,
                order_date TEXT NOT NULL,
                broker_order_no TEXT NOT NULL,
                fill_id TEXT NOT NULL,
                intent_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                applied INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_alias, order_date, broker_order_no, fill_id)
            );
            INSERT INTO fills_v2(account_alias,order_date,broker_order_no,fill_id,intent_id,payload,applied)
            SELECT COALESCE((SELECT p.account_alias FROM order_intents i JOIN profiles p ON p.profile_id=i.profile_id WHERE i.intent_id=f.intent_id),'default'),
                   COALESCE((SELECT i.session_date FROM order_intents i WHERE i.intent_id=f.intent_id),substr(json_extract(f.payload,'$.filled_at'),1,10)),
                   f.broker_order_no,f.fill_id,f.intent_id,f.payload,f.applied FROM fills f;
            DROP TABLE fills;
            ALTER TABLE fills_v2 RENAME TO fills;

            CREATE TABLE position_cycles (
                profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
                cycle_no INTEGER NOT NULL,
                status TEXT NOT NULL,
                entry_session TEXT NOT NULL,
                entry_at TEXT NOT NULL,
                exit_session TEXT,
                exit_at TEXT,
                starting_capital TEXT NOT NULL,
                capital_added TEXT NOT NULL DEFAULT '0',
                realized_pnl TEXT NOT NULL DEFAULT '0',
                final_state_hash TEXT,
                PRIMARY KEY(profile_id, cycle_no)
            );
            CREATE TABLE cycle_sessions (
                profile_id TEXT NOT NULL,
                cycle_no INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                trading_day_no INTEGER NOT NULL,
                calendar_day_no INTEGER NOT NULL,
                t TEXT NOT NULL,
                division_count INTEGER NOT NULL,
                mode TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                avg_cost TEXT NOT NULL,
                cash TEXT NOT NULL,
                invested TEXT NOT NULL,
                market_value TEXT,
                order_count INTEGER NOT NULL DEFAULT 0,
                fill_count INTEGER NOT NULL DEFAULT 0,
                cancel_count INTEGER NOT NULL DEFAULT 0,
                weather_payload TEXT,
                capital_payload TEXT,
                reconciliation_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(profile_id, cycle_no, session_date)
            );
            CREATE TABLE weather_snapshots (
                symbol TEXT NOT NULL,
                session_date TEXT NOT NULL,
                ruleset_version TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(symbol, session_date, ruleset_version)
            );
            CREATE TABLE capital_events (
                event_key TEXT PRIMARY KEY,
                account_alias TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount TEXT NOT NULL,
                settled INTEGER NOT NULL,
                profile_id TEXT,
                allocation_status TEXT NOT NULL DEFAULT 'unallocated',
                source_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE automation_claims (
                claim_key TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );
            CREATE TABLE capital_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                amount TEXT NOT NULL,
                timing TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX idx_order_intents_profile_status ON order_intents(profile_id,status,session_date);
            CREATE INDEX idx_broker_orders_status ON broker_orders(status,order_date);
            INSERT INTO schema_migrations(version, applied_at) VALUES (2, CURRENT_TIMESTAMP);
            """
        )
        db.execute("UPDATE profiles SET status='OFF' WHERE lower(status)='active'")
        db.execute("DROP TABLE IF EXISTS live_approvals")
        db.execute("DROP TABLE IF EXISTS scheduler_runs")

    def create_profile(self, profile: StrategyProfile) -> None:
        with self.connect() as db:
            duplicate = db.execute(
                "SELECT profile_id FROM profiles WHERE account_alias=? AND symbol=?",
                (profile.account_alias, profile.symbol),
            ).fetchone()
            if duplicate is not None:
                raise ValueError(f"account already has a profile for {profile.symbol}: {duplicate['profile_id']}")
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
            # Replanning may change quantity/price while the stable role identity
            # remains the same. Never let the previous unsubmitted plan linger.
            db.execute(
                """UPDATE order_intents SET status='STALE'
                   WHERE profile_id=? AND session_date=? AND phase=? AND status='PENDING' AND input_hash<>?""",
                (profile_id, session_date.isoformat(), phase.value, input_hash),
            )
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
            identity = db.execute(
                """SELECT p.account_alias,i.session_date FROM order_intents i JOIN profiles p ON p.profile_id=i.profile_id
                   WHERE i.intent_id=?""",
                (order.intent_id,),
            ).fetchone()
            if identity is None:
                raise KeyError(f"intent not found: {order.intent_id}")
            db.execute(
                """INSERT INTO broker_orders(account_alias,order_date,broker_order_no,intent_id,status,requested_qty,filled_qty,remaining_qty,submitted_at,last_checked_at,raw_response_hash)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    identity["account_alias"],
                    identity["session_date"],
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
            row = db.execute("SELECT profile_id FROM order_intents WHERE intent_id=?", (intent_id,)).fetchone()
            if row is not None:
                db.execute("UPDATE profiles SET status='LOCKED' WHERE profile_id=?", (row["profile_id"],))
                state_row = db.execute("SELECT payload,version FROM strategy_states WHERE profile_id=?", (row["profile_id"],)).fetchone()
                if state_row is not None:
                    state = _state_from_json(state_row["payload"])
                    if not state.reconciliation_required:
                        flagged = state.evolved(reconciliation_required=True)
                        db.execute(
                            "UPDATE strategy_states SET payload=?,version=?,updated_at=? WHERE profile_id=? AND version=?",
                            (canonical_json(flagged), flagged.version, _now(), flagged.profile_id, state.version),
                        )

    def has_order_for_intent(self, intent_id: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM broker_orders WHERE intent_id=?", (intent_id,)).fetchone() is not None

    def get_intent(self, intent_id: str) -> OrderIntent:
        with self.connect() as db:
            row = db.execute("SELECT payload FROM order_intents WHERE intent_id=?", (intent_id,)).fetchone()
        if row is None:
            raise KeyError(f"intent not found: {intent_id}")
        return _intent_from_json(row["payload"])

    def get_order(self, broker_order_no: str, account_alias: str | None = None, order_date: date | None = None) -> sqlite3.Row:
        with self.connect() as db:
            sql = "SELECT * FROM broker_orders WHERE broker_order_no=?"
            params: list[Any] = [broker_order_no]
            if account_alias is not None:
                sql += " AND account_alias=?"
                params.append(account_alias)
            if order_date is not None:
                sql += " AND order_date=?"
                params.append(order_date.isoformat())
            rows = db.execute(sql, params).fetchall()
        if not rows:
            raise KeyError(f"order not found: {broker_order_no}")
        if len(rows) > 1:
            raise KeyError(f"ambiguous order number; provide account and order date: {broker_order_no}")
        return rows[0]

    def update_order_status(
        self,
        broker_order_no: str,
        status: str,
        filled_qty: int,
        remaining_qty: int,
        account_alias: str | None = None,
        order_date: date | None = None,
    ) -> None:
        with self.connect() as db:
            sql = "UPDATE broker_orders SET status=?,filled_qty=?,remaining_qty=?,last_checked_at=? WHERE broker_order_no=?"
            params: list[Any] = [status, filled_qty, remaining_qty, _now(), broker_order_no]
            if account_alias is not None:
                sql += " AND account_alias=?"
                params.append(account_alias)
            if order_date is not None:
                sql += " AND order_date=?"
                params.append(order_date.isoformat())
            db.execute(sql, params)

    def list_orders(self, profile_id: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as db:
            if profile_id is None:
                return db.execute("SELECT b.* FROM broker_orders b ORDER BY submitted_at DESC").fetchall()
            return db.execute(
                """SELECT b.* FROM broker_orders b JOIN order_intents i ON i.intent_id=b.intent_id
                   WHERE i.profile_id=? ORDER BY b.submitted_at DESC""",
                (profile_id,),
            ).fetchall()

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
            identity = db.execute(
                """SELECT p.account_alias,i.session_date FROM order_intents i JOIN profiles p ON p.profile_id=i.profile_id
                   WHERE i.intent_id=?""",
                (fill.intent_id,),
            ).fetchone()
            if identity is None:
                raise KeyError(f"intent not found: {fill.intent_id}")
            cursor = db.execute(
                """INSERT OR IGNORE INTO fills(account_alias,order_date,broker_order_no,fill_id,intent_id,payload)
                   VALUES (?,?,?,?,?,?)""",
                (identity["account_alias"], identity["session_date"], fill.broker_order_no, fill.fill_id, fill.intent_id, canonical_json(fill)),
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
                db.execute("UPDATE fills SET applied=1 WHERE intent_id=? AND fill_id=?", (fill.intent_id, fill.fill_id))

    def set_profile_status(self, profile_id: str, status: str) -> None:
        normalized = status.upper()
        if normalized not in {"OFF", "ON", "LOCKED"}:
            raise ValueError("profile status must be OFF, ON, or LOCKED")
        with self.connect() as db:
            cursor = db.execute("UPDATE profiles SET status=? WHERE profile_id=?", (normalized, profile_id))
            if cursor.rowcount != 1:
                raise KeyError(f"profile not found: {profile_id}")
            db.execute("INSERT INTO audit_events(event_type,payload,created_at) VALUES (?,?,?)", ("PROFILE_STATUS", canonical_json({"profile_id": profile_id, "status": normalized}), _now()))

    def unresolved_orders(self, profile_id: str) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                """SELECT b.* FROM broker_orders b JOIN order_intents i ON i.intent_id=b.intent_id
                   WHERE i.profile_id=? AND b.status IN ('ACCEPTED','OPEN','PARTIAL','CANCEL_REQUESTED','UNKNOWN')
                   ORDER BY b.order_date,b.submitted_at""",
                (profile_id,),
            ).fetchall()

    def has_unknown_intents(self, profile_id: str) -> bool:
        with self.connect() as db:
            return db.execute(
                "SELECT 1 FROM order_intents WHERE profile_id=? AND status='UNKNOWN' LIMIT 1",
                (profile_id,),
            ).fetchone() is not None

    def save_weather(self, snapshot: WeatherSnapshot) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO weather_snapshots(symbol,session_date,ruleset_version,payload,created_at)
                   VALUES (?,?,?,?,?) ON CONFLICT(symbol,session_date,ruleset_version)
                   DO UPDATE SET payload=excluded.payload,created_at=excluded.created_at""",
                (snapshot.symbol, snapshot.session_date.isoformat(), snapshot.ruleset_version, canonical_json(snapshot), _now()),
            )

    def weather_history(self, symbol: str, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT payload FROM weather_snapshots WHERE symbol=? ORDER BY session_date DESC"
        params: list[Any] = [symbol.upper()]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.connect() as db:
            rows = db.execute(sql, params).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def record_capital_event(self, payload: dict[str, Any]) -> bool:
        required = {"account_alias", "occurred_at", "event_type", "currency", "amount", "settled"}
        missing = required - payload.keys()
        if missing:
            raise ValueError(f"capital event missing fields: {','.join(sorted(missing))}")
        source_hash = stable_hash(payload)
        event_key = str(payload.get("event_key") or source_hash)
        with self.connect() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO capital_events(event_key,account_alias,occurred_at,event_type,currency,amount,settled,profile_id,allocation_status,source_hash,payload,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_key,
                    payload["account_alias"],
                    str(payload["occurred_at"]),
                    payload["event_type"],
                    str(payload["currency"]).upper(),
                    str(payload["amount"]),
                    int(bool(payload["settled"])),
                    payload.get("profile_id"),
                    payload.get("allocation_status", "unallocated"),
                    source_hash,
                    canonical_json(payload),
                    _now(),
                ),
            )
            if cursor.rowcount == 1 and payload["event_type"] == "withdrawal" and not payload.get("authorized", False):
                profiles = db.execute("SELECT profile_id FROM profiles WHERE account_alias=?", (payload["account_alias"],)).fetchall()
                for profile in profiles:
                    db.execute("UPDATE profiles SET status='LOCKED' WHERE profile_id=?", (profile["profile_id"],))
                    state_row = db.execute("SELECT payload,version FROM strategy_states WHERE profile_id=?", (profile["profile_id"],)).fetchone()
                    if state_row is not None:
                        state = _state_from_json(state_row["payload"])
                        if not state.reconciliation_required:
                            flagged = state.evolved(reconciliation_required=True)
                            db.execute(
                                "UPDATE strategy_states SET payload=?,version=?,updated_at=? WHERE profile_id=? AND version=?",
                                (canonical_json(flagged), flagged.version, _now(), flagged.profile_id, state.version),
                            )
                db.execute(
                    "INSERT INTO audit_events(event_type,payload,created_at) VALUES ('UNEXPECTED_WITHDRAWAL',?,?)",
                    (canonical_json({"event_key": event_key, "account_alias": payload["account_alias"]}), _now()),
                )
            return cursor.rowcount == 1

    def capital_events(self, account_alias: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as db:
            if account_alias is None:
                return db.execute("SELECT * FROM capital_events ORDER BY occurred_at DESC").fetchall()
            return db.execute("SELECT * FROM capital_events WHERE account_alias=? ORDER BY occurred_at DESC", (account_alias,)).fetchall()

    def activate_next_cycle_capital(self, profile_id: str) -> Decimal:
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,amount FROM capital_allocations WHERE profile_id=? AND status='waiting_next_cycle' ORDER BY id",
                (profile_id,),
            ).fetchall()
            amount = sum((Decimal(row["amount"]) for row in rows), Decimal(0))
            if not rows:
                return amount
            db.executemany("UPDATE capital_allocations SET status='applied' WHERE id=?", [(row["id"],) for row in rows])
            profile = db.execute("SELECT capital FROM profiles WHERE profile_id=?", (profile_id,)).fetchone()
            db.execute("UPDATE profiles SET capital=? WHERE profile_id=?", (str(Decimal(profile["capital"]) + amount), profile_id))
            return amount

    def claim_automation(self, claim_key: str) -> bool:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO automation_claims(claim_key,status,created_at) VALUES (?,'CLAIMED',?)",
                (claim_key, _now()),
            )
            return cursor.rowcount == 1

    def finish_automation(self, claim_key: str, status: str) -> None:
        with self.connect() as db:
            db.execute("UPDATE automation_claims SET status=?,finished_at=? WHERE claim_key=?", (status, _now(), claim_key))

    def open_position_cycle(self, profile_id: str, cycle_no: int, entry_at: datetime, starting_capital: Decimal) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO position_cycles(
                    profile_id,cycle_no,status,entry_session,entry_at,starting_capital,capital_added,realized_pnl
                ) VALUES (?,?, 'OPEN', ?,?,?, '0','0')""",
                (profile_id, cycle_no, entry_at.date().isoformat(), entry_at.isoformat(), str(starting_capital)),
            )

    def close_position_cycle(self, profile_id: str, cycle_no: int, exit_at: datetime, realized_pnl: Decimal, state: StrategyState) -> None:
        with self.connect() as db:
            db.execute(
                """UPDATE position_cycles SET status='CLOSED',exit_session=?,exit_at=?,realized_pnl=?,final_state_hash=?
                   WHERE profile_id=? AND cycle_no=?""",
                (exit_at.date().isoformat(), exit_at.isoformat(), str(realized_pnl), stable_hash(state), profile_id, cycle_no),
            )

    def list_position_cycles(self, profile_id: str | None = None) -> list[sqlite3.Row]:
        with self.connect() as db:
            if profile_id is None:
                return db.execute("SELECT * FROM position_cycles ORDER BY profile_id,cycle_no DESC").fetchall()
            return db.execute("SELECT * FROM position_cycles WHERE profile_id=? ORDER BY cycle_no DESC", (profile_id,)).fetchall()

    def upsert_cycle_session(self, payload: dict[str, Any]) -> None:
        columns = (
            "profile_id",
            "cycle_no",
            "session_date",
            "trading_day_no",
            "calendar_day_no",
            "t",
            "division_count",
            "mode",
            "quantity",
            "avg_cost",
            "cash",
            "invested",
            "market_value",
            "order_count",
            "fill_count",
            "cancel_count",
            "weather_payload",
            "capital_payload",
            "reconciliation_status",
            "created_at",
        )
        values = [payload.get(column) for column in columns]
        with self.connect() as db:
            db.execute(
                f"""INSERT INTO cycle_sessions({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})
                    ON CONFLICT(profile_id,cycle_no,session_date) DO UPDATE SET
                    trading_day_no=excluded.trading_day_no,calendar_day_no=excluded.calendar_day_no,t=excluded.t,
                    division_count=excluded.division_count,mode=excluded.mode,quantity=excluded.quantity,avg_cost=excluded.avg_cost,
                    cash=excluded.cash,invested=excluded.invested,market_value=excluded.market_value,order_count=excluded.order_count,
                    fill_count=excluded.fill_count,cancel_count=excluded.cancel_count,weather_payload=excluded.weather_payload,
                    capital_payload=excluded.capital_payload,reconciliation_status=excluded.reconciliation_status,created_at=excluded.created_at""",
                values,
            )

    def list_cycle_sessions(self, profile_id: str, cycle_no: int) -> list[sqlite3.Row]:
        with self.connect() as db:
            return db.execute(
                "SELECT * FROM cycle_sessions WHERE profile_id=? AND cycle_no=? ORDER BY session_date",
                (profile_id, cycle_no),
            ).fetchall()

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

    def audit(self, event_type: str, payload: dict[str, Any]) -> None:
        with self.connect() as db:
            db.execute("INSERT INTO audit_events(event_type,payload,created_at) VALUES (?,?,?)", (event_type, canonical_json(payload), _now()))

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
        fee=Decimal(data.get("fee", "0")),
        settlement_status=data.get("settlement_status", "settled"),
        filled_at=datetime.fromisoformat(data["filled_at"]),
    )
