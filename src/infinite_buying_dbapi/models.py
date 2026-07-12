from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any

RULESET_VERSION = "pure-v4-ruleset-1"
SUPPORTED_SYMBOLS = {"TQQQ", "SOXL"}
SUPPORTED_DIVISIONS = {20, 30, 40}
LIVE_DIVISIONS = {20, 40}
ZERO = Decimal("0")


class Mode(StrEnum):
    NORMAL = "normal"
    REVERSE = "reverse"
    FLAT = "flat"


class Environment(StrEnum):
    PREVIEW = "preview"
    PAPER = "paper"
    LIVE = "live"


class Phase(StrEnum):
    SELL = "sell"
    BUY = "buy"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    LIMIT = "LIMIT"
    LOC = "LOC"
    MOC = "MOC"


class IntentRole(StrEnum):
    INITIAL_BUY = "initial_buy"
    AVG_HALF_BUY = "avg_half_buy"
    STAR_HALF_BUY = "star_half_buy"
    STAR_FULL_BUY = "star_full_buy"
    STAR_QUARTER_SELL = "star_quarter_sell"
    TARGET_SELL = "target_sell"
    REVERSE_FIRST_SELL = "reverse_first_sell"
    REVERSE_SELL = "reverse_sell"
    REVERSE_BUY = "reverse_buy"


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.normalize(), "f")


def canonical_json(value: Any) -> str:
    def default(item: Any) -> Any:
        if is_dataclass(item):
            return asdict(item)
        if isinstance(item, Decimal):
            return _decimal_text(item)
        if isinstance(item, (date, datetime)):
            return item.isoformat()
        if isinstance(item, StrEnum):
            return item.value
        raise TypeError(type(item).__name__)

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=default)


def stable_hash(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StrategyProfile:
    profile_id: str
    symbol: str
    division_count: int
    capital: Decimal
    account_alias: str = "default"
    ruleset_version: str = RULESET_VERSION
    status: str = "active"
    effective_from: date = field(default_factory=date.today)

    def __post_init__(self) -> None:
        symbol = self.symbol.upper()
        object.__setattr__(self, "symbol", symbol)
        if symbol not in SUPPORTED_SYMBOLS:
            raise ValueError(f"unsupported symbol: {symbol}")
        if self.division_count not in SUPPORTED_DIVISIONS:
            raise ValueError("division_count must be one of 20, 30, 40")
        if self.capital <= ZERO:
            raise ValueError("capital must be positive")
        if self.ruleset_version != RULESET_VERSION:
            raise ValueError(f"unsupported ruleset: {self.ruleset_version}")

    @property
    def target_pct(self) -> Decimal:
        return Decimal("0.20") if self.symbol == "SOXL" else Decimal("0.15")

    @property
    def live_eligible(self) -> bool:
        return self.division_count in LIVE_DIVISIONS and self.status == "active"


@dataclass(frozen=True, slots=True)
class StrategyState:
    profile_id: str
    cycle_id: str
    session_date: date
    cash: Decimal
    quantity: int = 0
    cost_basis: Decimal = ZERO
    t: Decimal = ZERO
    mode: Mode = Mode.NORMAL
    reverse_cash_pool: Decimal = ZERO
    reverse_cash_used: Decimal = ZERO
    reverse_days: int = 0
    last_5_closes: tuple[Decimal, ...] = ()
    version: int = 0
    reconciliation_required: bool = False

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise ValueError("quantity cannot be negative")
        if self.cash < ZERO or self.cost_basis < ZERO:
            raise ValueError("cash and cost_basis cannot be negative")
        if self.quantity == 0 and self.cost_basis != ZERO:
            raise ValueError("flat state cannot have cost basis")
        if len(self.last_5_closes) > 5 or any(value <= ZERO for value in self.last_5_closes):
            raise ValueError("last_5_closes must contain up to five positive prices")

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.quantity if self.quantity else ZERO

    @property
    def reverse_cash_remaining(self) -> Decimal:
        return max(ZERO, self.reverse_cash_pool - self.reverse_cash_used)

    def evolved(self, **changes: Any) -> "StrategyState":
        return replace(self, version=self.version + 1, **changes)


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    session_date: date
    previous_close: Decimal
    tick_size: Decimal = Decimal("0.01")
    completed_closes: tuple[Decimal, ...] = ()

    def __post_init__(self) -> None:
        if self.previous_close <= ZERO or self.tick_size <= ZERO:
            raise ValueError("prices and tick_size must be positive")
        if any(value <= ZERO for value in self.completed_closes):
            raise ValueError("completed closes must be positive")


@dataclass(frozen=True, slots=True)
class OrderIntent:
    intent_id: str
    input_hash: str
    cycle_id: str
    profile_id: str
    strategy_version: str
    session_date: date
    phase: Phase
    side: Side
    order_type: OrderType
    role: IntentRole
    quantity: int
    limit_price: Decimal | None
    budget: Decimal
    planned_t_effect: Decimal
    reason_code: str

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("intent quantity must be positive")
        if self.order_type in {OrderType.LIMIT, OrderType.LOC} and (self.limit_price is None or self.limit_price <= ZERO):
            raise ValueError("LIMIT and LOC orders need a positive limit price")
        if self.order_type == OrderType.MOC and self.limit_price is not None:
            raise ValueError("MOC cannot have a limit price")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FillEvent:
    broker_order_no: str
    fill_id: str
    intent_id: str
    side: Side
    role: IntentRole
    requested_qty: int
    filled_qty: int
    fill_price: Decimal
    filled_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not 0 < self.filled_qty <= self.requested_qty:
            raise ValueError("filled_qty must be between one and requested_qty")
        if self.fill_price <= ZERO:
            raise ValueError("fill_price must be positive")

    @property
    def fill_ratio(self) -> Decimal:
        return Decimal(self.filled_qty) / Decimal(self.requested_qty)


@dataclass(frozen=True, slots=True)
class BrokerOrder:
    broker_order_no: str
    intent_id: str
    status: str
    requested_qty: int
    filled_qty: int = 0
    remaining_qty: int = 0
    submitted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_checked_at: datetime | None = None
    raw_response_hash: str = ""


@dataclass(frozen=True, slots=True)
class AdvisoryProposal:
    proposal_id: str
    schema_version: str
    profile_id: str
    created_at: datetime
    valid_until: datetime
    proposal: dict[str, Any]
    explanation: str
    status: str = "rejected_by_default"
