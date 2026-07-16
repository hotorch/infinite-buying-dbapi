# V2 구현 계약

## 경계

- pure core: `models.py`, `strategy.py`; ruleset `pure-v4-ruleset-1` 불변
- broker/order safety: `broker.py`, `execution.py`, `reconciliation.py`
- SQLite v2: 복합 주문 식별자, outbox/fill, 회차·세션, 날씨, 자금 이벤트, 자동화 claim
- embedded weather: `weather.py`, ruleset `regime-weather-1`; 전략 입력과 자금 배분 입력으로 사용 금지
- operator API: `cli.py`; `--json`을 지원하는 V2 운영·조회 명령은 공통 JSON envelope 사용. `preview`와 최소 노출 `dbsec` 텍스트 출력은 예외
- Hermes: 기본 조회 전용. LLM 의견은 전략 상태나 broker payload를 바꿀 수 없고, 외부 일정/Slack은 저장소에서 구현하지 않음

## 상태 전이

프로필은 OFF/ON/LOCKED다. 새 프로필은 OFF다. ON은 자격증명 만료, capability, cron, 최신 날씨, 실제 잔고·주문가능금액, 대사 성공을 요구한다. OFF는 먼저 저장되고 그 다음 미체결 취소·대사가 실행된다. 불확실한 주문 결과는 UNKNOWN과 즉시 잠금을 원자적으로 기록한다.

## 저장소 버전

v1 데이터베이스는 시작 시 v2로 한 번 마이그레이션한다. broker order의 고유키는 `(account_alias, order_date, broker_order_no)`다. 계좌별 동일 종목 프로필은 하나만 허용한다. SQLite를 외부 대시보드 API로 쓰지 않고 `position`, `orders`, `automation` JSON 명령을 사용한다.

## 미검증 capability

실계좌 최소수량 LOC/LIMIT/MOC, 정정·취소, 부분체결, timeout 대사 증거가 `capabilities`에 `확인됨`으로 기록되기 전에는 ON을 거부한다. 입출금 원장 endpoint가 미확인인 동안 `capital scan`도 `CAPABILITY_NOT_VERIFIED`로 닫는다. endpoint나 응답 필드를 추측하지 않는다.
