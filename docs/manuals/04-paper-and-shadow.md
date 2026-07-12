# 04. 모의투자와 Shadow 운영

## 세 가지 검증 단계

1. `preview`: 계산만 확인
2. `paper`: 프로그램 내부 주문 접수 흐름 확인
3. DB증권 모의계좌: 실제 API 제약 확인

paper가 성공했다고 DB증권 API가 모든 주문을 지원한다는 뜻은 아닙니다.

## Paper 연습

```powershell
uv run app run sell-phase p1 --previous-close 100 --completed-closes 96,97,98,99,100 --environment paper
uv run app reconcile p1 --broker-quantity 0 --environment paper
uv run app run buy-phase p1 --previous-close 100 --completed-closes 96,97,98,99,100 --environment paper
uv run app orders list
```

같은 명령을 다시 실행해도 새 주문번호가 추가되지 않아야 합니다.

## DB증권 모의계좌에서 반드시 확인할 항목

- LOC 매도 접수
- 접수된 LOC 매도를 유지한 채 같은 종목 LOC 매수 접수
- 두 주문번호가 각각 조회되는지
- 매도 주문이 묶여 있어도 추가매수가 가능한지
- 미체결·부분체결·체결완료·거절 구분
- 정정과 취소
- 연속키가 있는 모든 페이지 조회
- 타임아웃 후 조회만으로 주문 성공 여부 복구

정확한 순서는 [테스트베드 프로토콜](../testbed-protocol.md)을 따르세요.

## 호출 제한 기록

사용하는 모든 TR의 공식 초당 전송 건수를 기록하고 그중 가장 낮은 값을 `.env`에 설정합니다.

```text
IB_DBSEC_REQUESTS_PER_SECOND=공식확인값
```

확인 전에는 값을 추정하지 않습니다. 여러 프로세스가 동시에 실행되어도 SQLite가 다음 호출 가능 시점을 공유합니다.

## Shadow 운영 20거래일

실제 주문 대신 매일 다음을 기록합니다.

- 생성된 주문 의도
- DB증권 앱에서 사람이 확인한 잔고·미체결
- 예상 체결과 실제 시장 종가
- 중복 주문 수
- 대조 실패 수
- 수동 DB 수정 여부

20개 미국 거래일 동안 중복 주문, 미대조 주문, 수동 DB 수정이 모두 0이어야 다음 단계로 갈 수 있습니다.
