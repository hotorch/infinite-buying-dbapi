import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from infinite_buying_dbapi.models import StrategyProfile
from infinite_buying_dbapi.strategy import star_pct


def test_ruleset_1_golden_vectors() -> None:
    rows = json.loads((Path(__file__).parent / "golden" / "ruleset_1_star_vectors.json").read_text(encoding="utf-8"))
    for row in rows:
        profile = StrategyProfile("golden", row["symbol"], row["division"], Decimal("10000"), effective_from=date(2026, 1, 2))
        assert star_pct(profile, Decimal(row["t"])) == Decimal(row["expected_star_pct"])
