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

```powershell
uv run app setup --account-alias student-001 --save-api-credentials
```

입력값은 화면에 표시되지 않습니다. `.env`나 소스 파일에는 저장하지 않습니다.

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

기본 `.env` 설정:

```text
IB_DBSEC_OAUTH_STYLE=json
```

최신 DB증권 안내 또는 고객센터 확인이 `form` 방식이라면:

```text
IB_DBSEC_OAUTH_STYLE=form
```

형식을 바꾼 뒤 1분 이내에 반복 발급하지 마세요.

## 프로그램의 토큰 처리

- 만료 5분 이상 남은 토큰은 재사용합니다.
- 만료가 가까우면 APP_KEY와 APP_SECRET으로 새 토큰을 발급합니다.
- 토큰 발급 요청은 계좌별 최소 60초 간격을 SQLite에서 강제합니다.
- 키·토큰·만료시각은 Windows 자격 증명 관리자에 보관합니다.
- 토큰 응답의 `access_token/expires_in`과 다운로드 명세의 `token/expire_in`을 모두 읽을 수 있습니다.

## 절대 하면 안 되는 일

- 키를 GitHub에 올리기
- 키가 보이는 화면을 강의 채팅방에 올리기
- 진단보고서에 키를 직접 복사하기
- 여러 수강생이 같은 APP_SECRET을 공유하기
- 토큰 오류가 날 때 1분 안에 계속 재시도하기
