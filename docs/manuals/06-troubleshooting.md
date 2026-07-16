# 06. 문제 해결

문제가 생기면 먼저 신규 주문을 막습니다.

```powershell
uv run app emergency-stop on
```

## `RECONCILIATION_REQUIRED`

뜻: DB증권과 로컬 프로그램의 수량 또는 주문이 일치하지 않습니다.

조치:

1. 새 주문을 보내지 않습니다.
2. DB증권 앱의 보유수량과 미체결 주문을 확인합니다.
3. `uv run app orders list`와 비교합니다.
4. 모르는 주문번호가 있으면 수동 주문 여부를 확인합니다.
5. 원인을 해결한 뒤 `uv run app reconcile --profile PROFILE --json`을 실행합니다.

## `OPPOSING_LOC_NOT_VERIFIED`

양방향 순차 LOC 모의시험을 통과하지 않았습니다. 실주문을 열지 말고 테스트베드 절차를 수행하세요.

## `RATE_LIMITS_NOT_VERIFIED`

사용 TR의 공식 호출 제한이 기록되지 않았습니다. 숫자를 추정해서 입력하지 마세요.

## `IB_DBSEC_REQUESTS_PER_SECOND must be set`

호출 제한은 확인됐지만 `.env` 설정이 없습니다. 공식 확인값 중 가장 낮은 값을 입력합니다.

## 토큰 발급 오류

확인 순서:

1. APP_KEY/APP_SECRET 만료 여부
2. 실계좌와 모의계좌 키 혼동 여부
3. `.env`의 `IB_DBSEC_OAUTH_STYLE=form` 확인
4. 마지막 발급 시도 후 60초 경과 여부
5. DB증권 공지·고객센터 확인

현재 실증된 기본값은 `form`입니다. 공식 홈페이지의 JSON 예시를 재현해야 하는 특별한 경우에만 `json`을 명시적으로 선택합니다. 두 OAuth 형식을 1분 안에 연속 시험하지 마세요.

HTTP 403이 나오면 먼저 `.env`에 예전 값인 `IB_DBSEC_OAUTH_STYLE=json`이 남아 있지 않은지 확인합니다. APP KEY·SECRET을 로그나 지원 채팅에 붙여 넣지 마세요.

HTTP 401·403·429 또는 5xx 오류가 나도 프로그램은 다른 OAuth 형식을 자동 재시도하지 않습니다. 오류에 표시된 `retry after` 시각 이후 원인을 확인하고 다시 실행하세요.

## 잔고 조회의 `2679 조회내역이 없습니다`

인증 실패가 아니라 요청한 해외주식 잔고 행이 없다는 DB증권 업무 응답입니다. 프로그램은 이를 빈 잔고로 처리합니다. DB증권 앱에 실제 해외주식이 있는데도 이 응답이 나오면 계좌·실계좌/모의계좌 키가 맞는지 확인하고 신규 주문을 중단하세요.

`uv run app dbsec holdings`가 빈 목록이고 로컬 프로필 수량도 0이면 정상 빈 상태입니다. 로컬 수량이 0이 아니면 `uv run app reconcile --profile PROFILE --json`으로 대사하세요. 불일치가 확인되면 `RECONCILIATION_REQUIRED`가 기록되고 신규 주문이 차단됩니다.

## 주문 결과가 불명확함

네트워크 타임아웃 후에도 주문은 성공했을 수 있습니다. 먼저 `uv run app emergency-stop on`으로 신규 주문을 막으세요. 같은 주문을 다시 보내지 말고 체결·미체결 조회와 앱 주문번호를 확인합니다. 프로그램은 해당 의도를 `UNKNOWN`으로 남겨 자동 재주문을 막습니다.

## `PROFILE_NOT_LIVE_ELIGIBLE`

30분할이거나 비활성 프로필입니다. 30분할을 이름만 바꿔 우회하지 마세요.

## 진단보고서 만들기

```powershell
uv run app diagnostics --output diagnostics/report.json --redacted
```

지원 담당자에게는 `--redacted` 보고서만 전달합니다.
