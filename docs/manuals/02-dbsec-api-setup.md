# 02. DB증권 Open API 신청과 인증

공식 안내: [DB증권 OPEN API 이용절차](https://openapi.dbsec.co.kr/howto-use)

## APP_KEY, APP_SECRET, Access Token의 차이

- `APP_KEY`: 계좌별 API 식별값
- `APP_SECRET`: APP_KEY의 비밀번호
- `Access Token`: 두 키로 발급하는 24시간짜리 임시 인증값

APP_KEY와 APP_SECRET을 Access Token이라고 부르는 경우가 있지만 서로 다른 값입니다. 프로그램에는 APP_KEY와 APP_SECRET을 한 번 안전하게 등록하고, Access Token은 프로그램이 필요할 때 발급받게 합니다.

## 공식 신청 순서

1. DB증권 계좌를 개설합니다.
2. DB증권 홈페이지에 공동인증서로 로그인합니다.
3. `온라인지점 > OpenAPI > OpenAPI 신청`으로 이동합니다.
4. 신청 가능한 계좌를 선택하고 약관에 동의합니다.
5. 사용 신청 후 APP_KEY와 APP_SECRET을 확인합니다.
6. 모의투자를 사용할 경우 모의투자용 키를 별도로 발급받습니다.

공식 페이지 기준 최대 3계좌까지 신청할 수 있습니다.

## 유효기간

| 값 | 개인 | 법인 |
|---|---:|---:|
| APP_KEY·APP_SECRET | 신청일부터 1년 | 신청일부터 3개월 |
| Access Token | 발급일부터 24시간 | 발급일부터 24시간 |

키 만료일은 캘린더에 미리 기록하세요. 키가 만료되면 토큰 재발급만 반복해서는 해결되지 않습니다.

## 프로그램에 키 저장

DB증권에서 내려받는 파일은 다음처럼 보일 수 있습니다.

```json
{
  "appkey": "발급받은 값",
  "appsecret": "발급받은 값",
  "env": "real",
  "expire_date": "YYYYMMDD"
}
```

이것은 `.env` 규격이 아니라 DB증권의 자격증명 전달 형식입니다. `env`와 `expire_date`는 발급 환경·만료 메타데이터이며 OAuth 요청 바디 필드가 아닙니다. `expire_date`는 APP KEY·SECRET 만료일이고 Access Token은 별도로 24시간 유효합니다.

권장 방법은 다음과 같이 직접 등록하는 것입니다.

```powershell
uv run app setup --account-alias student-001 --save-api-credentials
```

입력값은 화면에 표시되지 않습니다. `.env`나 소스 파일에는 저장하지 않습니다.

이미 `.env`에 네 값을 옮겨 놓았다면 일회성 가져오기를 실행할 수 있습니다.

```powershell
uv run app setup --account-alias student-001 --import-env-credentials
```

프로그램은 `DB_ENV=real`과 `DB_EXPIRE_DATE=YYYYMMDD`를 검증하고 APP KEY·SECRET만 OS keychain에 저장합니다. Windows에서는 자격 증명 관리자, macOS에서는 Keychain을 사용합니다. 성공 후 `.env`의 `DB_APPKEY`, `DB_APPSECRET` 줄을 삭제하세요.

## DB증권 문서의 OAuth 형식 차이

2026-07-12 기준 공식 홈페이지 이용절차는 다음 요청을 안내합니다.

```http
POST https://openapi.dbsec.co.kr:8443/oauth2/token
Content-Type: application/json
```

```json
{
  "grant_type": "client_credentials",
  "appkey": "발급받은 APP_KEY",
  "appsecret": "발급받은 APP_SECRET"
}
```

한편 공식 다운로드형 `OAuth 인증.xlsx`는 다음 형식을 안내합니다.

- `application/x-www-form-urlencoded`
- `appsecretkey`
- `scope=oob`

프로그램은 두 형식을 모두 지원하지만 자동으로 둘 다 시도하지 않습니다. 토큰 발급은 1분에 1회로 제한되기 때문입니다.

기본 `.env` 설정은 공식 다운로드 명세와 공식 테스트베드 샘플에 맞춘 다음 값입니다.

```text
IB_DBSEC_OAUTH_STYLE=form
```

홈페이지 이용절차의 JSON 예시를 특별히 재현할 때만 다음 호환 설정을 사용합니다.

```text
IB_DBSEC_OAUTH_STYLE=json
```

형식을 바꾼 뒤 1분 이내에 반복 발급하지 마세요.

2026-07-12 실제 발급 키로 `form` 인증을 호출해 HTTP 200과 `expires_in=86400`을 확인했습니다. 해외주식 잔고·증거금 API도 HTTP 200으로 도달했으며, 보유 잔고가 없는 계좌에서는 업무코드 `2679`, 메시지 `조회내역이 없습니다`가 반환됩니다. 프로그램은 이 응답을 빈 잔고로 처리합니다.

## 프로그램의 토큰 처리

- 만료 5분 이상 남은 토큰은 재사용합니다.
- 만료가 가까우면 APP_KEY와 APP_SECRET으로 새 토큰을 발급합니다.
- 토큰 발급 요청은 계좌별 최소 60초 간격을 SQLite에서 강제합니다.
- 키·토큰·만료시각은 OS keychain에 보관합니다.
- 토큰 응답의 `access_token/expires_in`과 다운로드 명세의 `token/expire_in`을 모두 읽을 수 있습니다.

등록 상태와 읽기 전용 연결 확인:

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
```

`auth-status`는 토큰을 새로 발급하지 않으며 자격증명 존재 여부, 발급 환경, 키 만료 여부, 캐시 토큰 유효 여부만 표시합니다.

## 절대 하면 안 되는 일

- 키를 GitHub에 올리기
- 키가 보이는 화면을 강의 채팅방에 올리기
- 진단보고서에 키를 직접 복사하기
- 여러 수강생이 같은 APP_SECRET을 공유하기
- 토큰 오류가 날 때 1분 안에 계속 재시도하기
