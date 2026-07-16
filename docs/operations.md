# 0.2.0 운영 명령 요약

모든 새 프로필은 `OFF`로 만들어지고, 비상정지는 `ON`으로 시작한다. `preview`는 계산만 하며 주문이나 전략 상태를 기록하지 않는다.

## 1. 처음 준비

```powershell
uv run app setup --account-alias student-001 --save-api-credentials --credential-expire-date YYYYMMDD --tqqq-capital 10000 --soxl-capital 10000
uv run app weather update --symbol TQQQ --json
uv run app automation readiness --profile tqqq
```

- `IB_DBSEC_ACCOUNT_MODE=real`이 기본이다.
- 제거된 `IB_ENVIRONMENT`가 남아 있으면 프로그램이 중단된다.
- APP KEY, APP SECRET, access token은 OS keychain에만 저장한다.
- `weather update`는 DB증권 일봉을 조회하고 로컬 시장 데이터와 날씨를 갱신한다.
- `readiness`는 DB증권 조회와 대사를 포함한다. 단순 로컬 조회가 아니다.

## 2. 안전한 조회

```powershell
uv run app automation status tqqq --json
uv run app position status tqqq --json
uv run app position cycles tqqq --json
uv run app position sessions tqqq --cycle 1 --json
uv run app orders list --profile tqqq --json
uv run app weather current --symbol TQQQ --json
uv run app capital status
uv run app report daily --session-date latest --json
```

Hermes는 기본적으로 위 조회와 결과 설명만 수행한다. 날씨와 LLM 의견은 전략 주문이나 자금 배분을 바꾸지 않는다.

## 3. ON과 자동 실행

ON은 다음 조건을 모두 통과해야 한다.

- 20분할 또는 40분할
- 유효한 자격증명
- 비상정지 해제
- 최신 날씨
- 필요한 capability와 실계좌 인수시험 증거
- DB증권과 로컬 상태 대사 성공
- 첫 ON이면 대상 보유·미체결 0건
- 결제완료 주문가능 USD 존재
- 외부 실행 일정 확인

사용자가 비상정지 해제와 정확한 프로필 ON을 명시적으로 승인한 뒤에만 실행한다.

```powershell
uv run app emergency-stop off
uv run app automation readiness --profile tqqq
uv run app automation on --profile tqqq --cron-verified
uv run app automation status tqqq --json
```

`automation tick --all --quiet-when-idle`은 시각 조회가 아니다. ON 프로필에서 실제 주문을 실행할 수 있다. 외부 일정과 메시지 전달은 저장소 밖에서 사용자가 구성한다.

## 4. 정상 중지

```powershell
uv run app automation off --profile tqqq
```

이 명령은 먼저 OFF를 저장한 뒤 미체결 취소와 재조회를 시도한다. 취소 결과가 불명확하면 `LOCKED + reconciliation_required`로 남는다. 같은 취소를 반복하지 않는다.

## 5. UNKNOWN 또는 불일치

다음 순서로 신규 주문을 막고 증거를 보존한다.

```powershell
uv run app emergency-stop on
uv run app orders list --profile tqqq --json
uv run app backup create backups/before-reconcile.sqlite3
uv run app reconcile --profile tqqq --json
uv run app diagnostics --output diagnostics/report.json --redacted
```

- 같은 주문이나 취소를 다시 보내지 않는다.
- SQLite를 직접 수정하지 않는다.
- 진단 파일은 `--redacted` 상태로만 전달한다.
- `LOCKED`를 임의로 OFF나 ON으로 바꾸지 않는다.

Hermes에게는 [Hermes 프로젝트 핸드오프](hermes-handoff.md)를 먼저 전달한다. Hermes skill, cron, Slack, Gateway는 사용자가 별도 환경에서 구성한다.
