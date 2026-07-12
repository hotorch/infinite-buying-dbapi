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
5. 원인을 해결한 뒤 `reconcile`을 다시 실행합니다.

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
3. `IB_DBSEC_OAUTH_STYLE=json` 또는 `form` 선택
4. 마지막 발급 시도 후 60초 경과 여부
5. DB증권 공지·고객센터 확인

두 OAuth 형식을 1분 안에 연속 시험하지 마세요.

## 주문 결과가 불명확함

네트워크 타임아웃 후 주문이 성공했을 수도 있습니다. 같은 주문을 다시 보내지 말고 체결·미체결 조회와 앱 주문번호를 먼저 확인하세요. 프로그램은 해당 의도를 `UNKNOWN`으로 남겨 자동 재주문을 막습니다.

## `PROFILE_NOT_LIVE_ELIGIBLE`

30분할이거나 비활성 프로필입니다. 30분할을 이름만 바꿔 우회하지 마세요.

## 진단보고서 만들기

```powershell
uv run app diagnostics --output diagnostics/report.json --redacted
```

지원 담당자에게는 `--redacted` 보고서만 전달합니다.
