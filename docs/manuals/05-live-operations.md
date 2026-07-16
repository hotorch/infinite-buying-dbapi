# 05. 실주문 운영

실주문은 강사 계좌 최소수량 인수시험과 모든 readiness 조건을 통과한 뒤에만 사용할 수 있습니다. 조건이 하나라도 빠지면 ON이 실패하는 것이 정상입니다.

## Hermes의 기본 권한

Hermes는 기본적으로 상태를 조회하고 결과를 설명합니다. Hermes의 시장 의견이나 날씨 값은 주문 가격·수량·`T`·자금 배분을 바꿀 수 없습니다.

`automation on`, `automation off`, `automation tick`, `reconcile`, `capital apply`, `emergency-stop on/off`는 상태나 실계좌에 영향을 줄 수 있습니다. Hermes는 사용자가 정확한 명령과 대상을 명시한 경우에만 해당 명령을 실행합니다.

## ON 전 확인

```powershell
uv run app automation readiness --profile p1
uv run app automation status p1 --json
```

readiness는 다음 항목을 확인합니다.

- 프로필이 `LOCKED`가 아님
- 20분할 또는 40분할
- 자격증명이 있고 만료되지 않음
- 비상정지가 해제됨
- 최신 날씨가 있음
- 필요한 capability와 실계좌 시험 증거가 확인됨
- DB증권과 로컬 수량이 일치함
- 첫 ON이면 대상 종목 보유와 미체결이 없음
- 결제완료 주문가능 USD가 있음
- 외부 실행 일정이 확인됨

사용자가 비상정지 해제와 정확한 프로필 ON을 승인한 경우에만 실행합니다. 비상정지를 해제한 뒤 readiness를 다시 확인합니다.

```powershell
uv run app emergency-stop off
uv run app automation readiness --profile p1
uv run app automation on --profile p1 --cron-verified
uv run app automation status p1 --json
```

## 자동 실행 명령 주의

프로젝트가 제공하는 자동 실행 진입점은 다음과 같습니다.

```powershell
uv run app automation tick --all --quiet-when-idle
```

이 명령은 단순한 시각 확인이 아닙니다. 미국 거래소 일정과 현재 단계를 계산한 뒤 ON 프로필에서 실제 주문을 실행할 수 있습니다. 실행 주기, Hermes skill, Slack 전달 방식은 사용자가 저장소 밖에서 구성합니다.

## 정상적으로 중지

```powershell
uv run app automation off --profile p1
```

이 명령은 다음 순서로 동작합니다.

1. 신규 주문을 막기 위해 먼저 프로필을 OFF로 저장합니다.
2. 남은 미체결 주문의 취소를 요청합니다.
3. DB증권에서 결과를 다시 확인합니다.

취소 결과가 불명확하면 `LOCKED + reconciliation_required`로 남습니다. 같은 취소를 반복하거나 SQLite를 직접 고치지 마세요.

## UNKNOWN 또는 불일치가 생겼을 때

```powershell
uv run app emergency-stop on
uv run app orders list --profile p1 --json
uv run app backup create backups/before-reconcile.sqlite3
uv run app reconcile --profile p1 --json
uv run app report daily --session-date latest --json
```

같은 주문을 다시 보내지 않습니다. DB증권 앱의 보유수량·미체결과 로컬 출력이 일치하는지 확인합니다. 원인이 해결되지 않으면 `LOCKED`를 유지합니다.

20분할과 40분할만 실주문 후보입니다. 30분할은 preview와 백테스트 전용입니다. 날씨가 orange 또는 red여도 진행 중인 V4 주문은 바뀌지 않습니다.
