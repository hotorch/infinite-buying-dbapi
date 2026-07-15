# 05. 실주문 운영

강사 실계좌 최소수량 인수시험 증거와 Hermes cron이 모두 확인되기 전에는 ON이 실패하는 것이 정상이다.

```powershell
uv run app automation readiness --profile p1
uv run app automation on --profile p1 --cron-verified
uv run app automation status p1 --json
```

Hermes의 `live-runner`가 5분마다 `automation tick --all --quiet-when-idle`을 실행한다. 앱이 XNYS 거래일·DST·단계를 판단하고 중복 claim과 주문 후 대사를 수행한다. 변화가 없으면 stdout이 비어 Slack 메시지가 없다.

중지 요청은 다음 한 명령으로 처리한다.

```powershell
uv run app automation off --profile p1
```

이 명령은 OFF를 먼저 저장하고 미체결 취소·재조회를 한다. 결과가 불명확하면 LOCKED로 남으므로 재시도하거나 SQLite를 고치지 말고 다음을 확인한다.

```powershell
uv run app reconcile --profile p1 --json
uv run app orders list --profile p1 --json
uv run app report daily --session-date latest --json
```

division 20/40만 실주문 가능하다. 날씨가 orange/red여도 진행 회차의 V4 주문은 바뀌지 않는다.
