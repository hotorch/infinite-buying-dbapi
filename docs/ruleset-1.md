# `pure-v4-ruleset-1` decision record

All money and price calculations use `Decimal`; share quantities are positive
integers. Strategy capital is denominated in US dollars in v1.

## Normal mode

- TQQQ target: 15%; SOXL target: 20%.
- `star_pct = target_pct - (target_pct * 2 / divisions) * T`.
- `star_price = average_cost * (1 + star_pct)`.
- Initial LOC limit: previous completed official close times 1.20. This is an
  explicit ruleset-1 choice, not claimed as an official source number.
- Dynamic tranche: `cash / (divisions - T)` while the denominator is greater
  than one.
- Front half: half tranche at average cost and half below star.
- Back half: one full tranche below star.
- No speculative top-up LOC is generated for integer-share budget residue.
- Sell `max(1, floor(quantity / 4))` at star LOC and the remainder at the target
  limit. Their total never exceeds holdings.

## Fill transitions

- Normal buy: add `planned_delta * filled/requested` to T.
- Quarter sell: multiply T by `1 - 0.25 * filled/requested`.
- Target sell: multiply T by `1 - 0.75 * filled/requested`.
- Reverse sell: multiply T by `1 - (2/divisions) * filled/requested`.
- Reverse buy: add `(divisions - T) * 0.25 * filled/requested`.
- Broker timestamp orders events. Equal timestamps apply sells before buys.

## Reverse mode

- Enter when `T > divisions - 1`; freeze current cash as the reverse cash pool.
- First session: sell `max(1, floor(quantity * 2 / divisions))` by MOC; no buy.
- Later sessions: use the average of up to five completed closes as reverse
  star, sell at LOC, and buy below star.
- Each reverse buy may use at most one quarter of the entry cash pool, with
  prior reverse purchases deducted.
- Return to normal on the next session when previous close is above 85% of
  TQQQ average cost or 80% of SOXL average cost.

Division 30 uses the generalized formula but is backtest/preview only and can never be enabled for real orders.
Ruleset changes require a new identifier and new golden vectors.
