from __future__ import annotations

import importlib.util
from pathlib import Path


def test_distributed_market_data_passes_validation() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "validate_market_data.py"
    spec = importlib.util.spec_from_file_location("validate_market_data", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    summaries = module.validate_all()

    assert {summary["file"] for summary in summaries} == {
        "qqq_adjusted_daily.csv",
        "smh_adjusted_daily.csv",
        "soxl_adjusted_daily.csv",
        "spy_adjusted_daily.csv",
        "tqqq_adjusted_daily.csv",
    }
