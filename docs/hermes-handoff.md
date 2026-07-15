# Hermes 운영 핸드오프

## 고정 계약

- 애플리케이션 `0.2.x`, 전략 `pure-v4-ruleset-1`, 날씨 `regime-weather-1`을 고정한다.
- Hermes는 이 저장소의 `uv run app ...` JSON 명령만 호출한다. 코드, 환경변수, SQLite, broker payload를 수정하지 않는다.
- TQQQ 신호는 QQQ, SOXL 신호는 SMH, 공통 벤치마크는 SPY다. 날씨는 신규 결제완료 USD 배분과 설명에만 쓰며 V4 주문·`T`·역방향 모드·진행 회차를 변경하지 않는다.
- `T`는 전략 진행값이고 거래일차가 아니다. 첫 BUY 체결로 회차가 열리고 수량을 0으로 만드는 SELL 체결로 닫힌다. 같은 시각은 SELL 후 BUY라서 청산 직후 BUY는 새 회차다.
- OFF는 신규 주문을 먼저 막은 뒤 미체결을 취소·재조회한다. UNKNOWN, timeout, network, HTTP 5xx, 비정상 주문 JSON, 대사 불일치는 재시도하지 않고 `LOCKED + reconciliation_required`로 둔다.
- 진행 회차 신규 자금은 `현재 T·원가 유지 후 cash 증액` 또는 `다음 회차까지 미배정`만 제안한다. 답이 없으면 미배정으로 둔다.

## Slack과 Gateway

Hermes 공식 Slack 설정에서 Member ID 기반 `SLACK_ALLOWED_USERS`, 채널 ID 기반 `SLACK_ALLOWED_CHANNELS`, cron 기본 전달 대상인 `SLACK_HOME_CHANNEL`을 모두 설정한다. 봇을 home channel에 초대한다. 토큰은 Hermes 저장소와 OS keychain에만 두고 이 저장소에는 넣지 않는다. 자세한 필드와 설치 순서는 [Hermes Slack 공식 문서](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/slack/)를 따른다.

## cron 세 개

공식 [Hermes cron 계약](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron)에 따라 통합 `cronjob` 도구로 생성·목록 확인·pause/resume한다. 절대 경로 `workdir`를 지정한다. cron 안에서는 cron을 다시 만들 수 없다.

1. `live-runner`: `every 5m`, `no_agent=true`, `~/.hermes/scripts/infinite_buying_runner.py live`, Slack delivery. stdout이 비면 전달되지 않고 nonzero는 경고가 된다.
2. `capital-watch`: `every 30m`, `no_agent=true`, 같은 wrapper의 `capital` 모드. 새 결제완료 USD 이벤트가 있을 때만 출력한다.
3. `morning-report`: `0 8 * * *`, timezone `Asia/Seoul`, `operate-infinite-buying` skill을 붙이고 `app report daily --session-date latest --json`만 근거로 한국어 보고를 만든다.

세 작업을 list/검증한 뒤 `automation on --profile ... --cron-verified`를 실행한다. 모든 프로필이 OFF면 `live-runner`를 pause한다.

## 대화 예시

- `TQQQ 실주문 시작` → cron 확인 → readiness → blocker 보고 또는 ON
- `SOXL 꺼줘` → OFF → 취소·대사 결과 보고
- `이번 입금은 다음 회차` → capital status에서 정확한 결제완료 이벤트 확인 → next_cycle 배정
- `현재 회차와 오늘 날씨 보고` → position status + weather current
- `미체결 전부 정리` → 대상 프로필 OFF; 직접 cancel 반복 금지

코드 변경이 필요하면 모든 프로필을 OFF하고 미체결 0 및 대사 OK를 확인한 뒤 별도의 개발·테스트 절차로 넘긴다.

설치 가능한 skill은 `hermes-skills/operate-infinite-buying/`에 있다.
