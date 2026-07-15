# DB증권 강사 실계좌 최소수량 인수시험

DB증권 모의계좌 동작을 실계좌 capability 증거로 대체하지 않는다. 강사 소유 실계좌에서 대상 종목 1주와 감당 가능한 가격만 사용한다. 요청·응답 원문이나 계좌번호 대신 redacted hash, 응답 코드, 복합 주문 식별자, 시각, 앱 화면, 최종 대사 결과를 보관한다.

1. 신규 DB와 OS keychain 자격증명으로 시작하고 대상 종목 보유·미체결 0, 결제완료 USD, 최신 수정 일봉을 확인한다.
2. LOC·LIMIT·MOC를 각각 1주 최소수량으로 제출하고 주문번호와 재조회 가능 여부를 확인한다. 시장 상황상 체결을 유도하지 않는다.
3. 정정 1회와 취소 1회를 수행하고 최종 상태를 재조회한다. 불명확한 취소를 반복하지 않는다.
4. 동일 종목 opposing LOC가 필요한 Pure V4 순서를 1주로 확인한다. 보유수량을 초과하는 매도는 절대 제출하지 않는다.
5. 자연 발생한 부분체결이 있을 때만 체결수량·잔량·평단·현금·수수료·결제상태가 취소 후에도 보존되는지 검증한다.
6. 전용 fault-injection proxy가 실제 제출 후 응답만 끊는 승인된 시험에서 timeout을 1회 만든다. 같은 intent를 재전송하지 않고 다음날까지 transaction history로 추적한다.
7. 429, 5xx, 비정상 JSON fixture 계약 시험과 실계좌 read-only pagination 증거를 별도로 보관한다.
8. 마지막에 보유수량, 현금, 미체결, 수수료, 결제상태를 대사하고 프로필 OFF 자동취소를 확인한다.

실제 주문을 일부러 중복 제출해 idempotency를 시험하지 않는다. broker order number는 `(account_alias, order_date, broker_order_no)`로 기록한다.

모든 항목이 성공하고 증거가 검토된 경우에만 강사가 다음을 실행한다.

```powershell
uv run app capability verify --opposing-loc-confirmed --rate-limits-confirmed --live-order-tests-confirmed --evidence "redacted report path, account alias, date"
```

부분체결 또는 timeout 실증을 수행하지 못했다면 해당 capability는 `확인 필요`로 남기며 ON은 계속 차단한다.
