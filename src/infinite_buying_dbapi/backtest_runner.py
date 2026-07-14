from __future__ import annotations

import json
import sys

from .backtest import BacktestError, run_backtest


def main() -> int:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        request = json.load(sys.stdin)
        result = run_backtest(request)
    except BacktestError as error:
        json.dump({"error": {"code": error.code, "message": str(error), "details": error.details}}, sys.stdout, ensure_ascii=False)
        return 2
    except (json.JSONDecodeError, TypeError):
        json.dump({"error": {"code": "INVALID_JSON", "message": "요청 내용을 읽을 수 없습니다.", "details": {}}}, sys.stdout, ensure_ascii=False)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
