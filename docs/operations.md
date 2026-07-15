# V2 운영 명령

모든 실계좌 프로필은 `OFF`로 생성된다. `preview`는 계산만 하며 SQLite와 outbox를 변경하지 않는다.

```powershell
uv run app setup --account-alias student-001 --save-api-credentials --credential-expire-date YYYYMMDD --tqqq-capital 10000 --soxl-capital 10000
uv run app weather update --symbol TQQQ --json
uv run app automation readiness --profile tqqq
```

`IB_DBSEC_ACCOUNT_MODE=real`이 기본이다. `IB_ENVIRONMENT`는 제거되었으며 존재하면 명시적 오류가 난다. APP KEY·SECRET·토큰은 OS keychain에만 둔다.

Hermes cron 3개를 생성·검증한 뒤에만 다음을 실행한다.

```powershell
uv run app automation on --profile tqqq --cron-verified
uv run app automation status tqqq --json
```

OFF는 신규 주문을 먼저 막고 미체결 취소·재조회를 수행한다. 결과가 불명확하면 `LOCKED`로 남는다.

```powershell
uv run app automation off --profile tqqq
uv run app reconcile --profile tqqq --json
```

Hermes용 안정적인 조회 명령:

```powershell
uv run app position status tqqq --json
uv run app position cycles tqqq --json
uv run app position sessions tqqq --cycle 1 --json
uv run app orders list --profile tqqq --json
uv run app weather current --symbol TQQQ --json
uv run app capital status
uv run app report daily --session-date latest --json
```

UNKNOWN, 수량·현금 불일치, 비정상 출금 또는 데이터 오류가 있으면 재전송하지 않는다. SQLite를 직접 고치지 말고 `emergency-stop on`, 백업, 대사 순서로 처리한다.

Hermes 설치·cron·Slack 계약은 [Hermes 핸드오프](hermes-handoff.md)를 따른다.
