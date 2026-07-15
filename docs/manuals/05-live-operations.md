# 05. 실주문 운영

강사 실계좌 최소수량 인수시험 증거와 사용자의 외부 Hermes 실습 준비가 모두 확인되기 전에는 ON이 실패하는 것이 정상이다.

```powershell
uv run app automation readiness --profile p1
uv run app automation on --profile p1 --cron-verified
uv run app automation status p1 --json
```

외부 실행 방식은 사용자가 Hermes 실습에서 직접 정한다. 프로젝트가 제공하는 실행 명령은 `automation tick --all --quiet-when-idle`이며, 앱이 XNYS 거래일·DST·단계를 판단하고 중복 claim과 주문 후 대사를 수행한다. 실행 주기나 전달 방식은 이 문서에서 정하지 않는다.

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
