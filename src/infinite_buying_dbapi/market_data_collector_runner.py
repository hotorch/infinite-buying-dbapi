from __future__ import annotations

import json

from .cli import _read_only_broker
from .market_data import collect_market_data, market_data_status


def main() -> None:
    try:
        status = market_data_status()
        result = collect_market_data(_read_only_broker()[0]) if status["needs_update"] else {
            "latest_completed_session": status["latest_completed_session"],
            "updated": False,
            "added": 0,
            "symbols": [
                {
                    "symbol": item["symbol"],
                    "previous_last_date": item["last_date"],
                    "last_date": item["last_date"],
                    "added": 0,
                }
                for item in status["symbols"]
            ],
        }
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": {"code": "MARKET_DATA_COLLECTION_FAILED", "message": str(exc)}}, ensure_ascii=False, separators=(",", ":")))
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
