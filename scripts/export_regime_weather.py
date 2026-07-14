from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

DEFAULT_SOURCE_REPO = Path(r"C:\Users\hoyoung\Desktop\lazy-codex-toss-trading")
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "market" / "tqqq_regime_weather.csv"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export TQQQ regime weather rows from the EXP-009 decision engine."
    )
    parser.add_argument("--source-repo", type=Path, default=DEFAULT_SOURCE_REPO)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source_repo = args.source_repo.resolve()
    sys.path.insert(0, str(source_repo))
    sys.path.insert(0, str(source_repo / "scripts" / "analysis"))

    from tqqq_soxl_listing_walk_forward import DATA_DIR, read_candles, validate_candles
    from trading_bot.config import load_universe
    from trading_bot.decision_core import _align_pair_market, _gate_status, load_policy_profile
    from trading_bot.indicators import snapshot

    market = {}
    for symbol in ("QQQ", "SMH", "SPY", "TQQQ", "SOXL"):
        candles = read_candles(DATA_DIR / f"{symbol}_adjusted_daily.csv")
        validate_candles(symbol, candles)
        market[symbol] = candles

    profile_path = source_repo / "config" / "policy_profiles" / "live_2026h1.json"
    universe_path = source_repo / "config" / "leveraged_etf_universe.json"
    config = load_policy_profile(profile_path).to_infinite_config()
    pair = next(pair for pair in load_universe(universe_path) if pair.trade_symbol == "TQQQ")
    aligned, dates = _align_pair_market(pair, market, include_signal=True)

    rows: list[dict[str, object]] = []
    previous_regime: str | None = None
    regime_age = 0
    strong_green_age = 0
    last_stress_cursor: int | None = None

    for cursor in range(config.min_history, len(dates) - 1):
        window_start = max(0, cursor - 319)
        window = {symbol: candles[window_start : cursor + 1] for symbol, candles in aligned.items()}
        window_cursor = len(window[pair.trade_symbol]) - 1
        gate = _gate_status(pair, window, window_cursor, config)
        signal = snapshot(pair.signal_symbol, window[pair.signal_symbol], window[pair.benchmark_symbol])
        trade = snapshot(pair.trade_symbol, window[pair.trade_symbol], window[pair.benchmark_symbol])

        regime_age = regime_age + 1 if gate.regime == previous_regime else 1
        strong_green_age = strong_green_age + 1 if gate.regime == "strong_green" else 0
        if gate.regime in {"orange", "red"}:
            last_stress_cursor = cursor
        sessions_since_stress = cursor - last_stress_cursor if last_stress_cursor is not None else None

        signal_closes = [candle.close for candle in window[pair.signal_symbol][-60:]]
        sma50_now = sum(signal_closes[-50:]) / 50.0
        sma50_10ago = sum(signal_closes[-60:-10]) / 50.0 if len(signal_closes) >= 60 else sma50_now
        distance_50 = signal.close / signal.sma50 - 1.0 if signal.sma50 else None
        early_thaw = bool(
            gate.regime in {"green", "yellow"}
            and signal.return_3m is not None
            and 0.0 <= signal.return_3m <= 0.08
            and 0.0 <= signal.rs_score <= 0.08
            and distance_50 is not None
            and 0.0 <= distance_50 <= 0.05
            and sma50_now > sma50_10ago
            and sessions_since_stress is not None
            and sessions_since_stress <= 60
        )

        reasons = list(gate.reasons)
        if gate.hard_break_reason and gate.hard_break_reason not in reasons:
            reasons.insert(0, gate.hard_break_reason)
        rows.append(
            {
                "date": dates[cursor + 1].isoformat(),
                "signal_date": dates[cursor].isoformat(),
                "symbol": pair.trade_symbol,
                "signal_symbol": pair.signal_symbol,
                "regime": gate.regime,
                "weather_state": "early_thaw" if early_thaw else gate.regime,
                "regime_age": regime_age,
                "strong_green_age": strong_green_age,
                "score": round(gate.score, 10),
                "signal_return_3m": round(signal.return_3m, 10) if signal.return_3m is not None else "",
                "signal_return_6m": round(signal.return_6m, 10) if signal.return_6m is not None else "",
                "signal_rs": round(signal.rs_score, 10),
                "signal_distance_50": round(distance_50, 10) if distance_50 is not None else "",
                "signal_sma50_rising_10d": sma50_now > sma50_10ago,
                "sessions_since_stress": sessions_since_stress if sessions_since_stress is not None else "",
                "trade_dollar_volume_multiple": round(trade.dollar_volume / config.min_dollar_volume, 4),
                "reasons": "|".join(reasons),
            }
        )
        previous_regime = gate.regime

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"rows={len(rows)}")
    print(f"date_range={rows[0]['date']}..{rows[-1]['date']}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
