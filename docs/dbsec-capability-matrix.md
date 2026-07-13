# DB Securities capability matrix

Checked against the official service pages and the downloaded overseas-order
workbook on 2026-07-12. Runtime evidence is stored in SQLite by
`app capability verify`.

| Capability | Status | Evidence / required action |
|---|---|---|
| US stock/ETF order | 확인됨 | Overseas stock order API; overseas ETF service registration is required |
| Test-account order | 확인됨 | Official order description |
| Limit / LOC / MOC | 확인됨 | `AstkOrdprcPtnCode` 1 / 5 / 6 |
| Correction / cancellation | 확인됨 | `OrdTrdTpCode` 1 / 2 with original order number |
| Fill and unfilled inquiry | 문서·CLI 구현 확인 / 실응답 미검증 | `/api/v1/trading/overseas-stock/inquiry/transaction-history`; read-only CLI and pagination are implemented |
| Holdings / margin | 확인됨 | `/api/v1/trading/overseas-stock/inquiry/balance-margin`; 2026-07-12 real-key read-only call reached HTTP 200, with `2679` meaning no rows |
| Opposing LOC on one symbol | 확인 필요 | Must pass `docs/testbed-protocol.md` |
| Buy while sell shares are reserved | 확인 필요 | Must pass testbed protocol |
| OAuth issue / renewal | 확인됨 | 2026-07-12 real-key form OAuth returned HTTP 200 and `expires_in=86400`; one issuance request per minute; JSON remains explicit compatibility only |
| OAuth revoke | 문서 확인됨 / 실증 필요 | `/oauth2/revoke` schema is implemented but was not called with the user's real token |
| Orderable amount request schema | 확인됨 | `/api/v1/trading/overseas-stock/inquiry/able-orderqty`; `TrxTpCode`, symbol, price, currency code |
| Current price / daily chart schema | 문서·CLI 구현 확인 / 실응답 미검증 | `/api/v1/quote/overseas-stock/inquiry/price` and `/api/v1/quote/overseas-stock/chart/day` |
| Broker idempotency key | 확인 필요 | Not present in the order workbook; test and ask DB Securities |
| Rate limits | 확인 필요 | Record every used TR limit, configure the lowest value, then mark verified; SQLite enforces a cross-process interval |
| KRW settlement | 대체 설계 필요 | v1 live accounting is USD-only |
| Early-close broker cutoff | 확인 필요 | Scheduler assumes documented close-minus-10-minutes, then test |

`supports_opposing_loc` must equal `확인됨` before installation live enablement.
If the test fails, automatic live orders remain disabled; the strategy is not
silently modified.
