# 순수 무한매수 V4 + DB증권 자동매매

DB증권 Open API를 이용해 `순수 무한매수 V4` 규칙을 계산하고, 주문을 안전하게 준비·기록·대조하는 Windows용 프로그램입니다.

처음 사용하는 분은 이 README를 위에서부터 차례로 따라 하세요. 세부 설명은 [전체 매뉴얼 목차](docs/manuals/README.md)에 따로 정리되어 있습니다.

> [!WARNING]
> 이 프로그램은 투자 권유나 수익 보장 도구가 아닙니다. 레버리지 ETF는 큰 손실이 발생할 수 있습니다. 처음에는 반드시 `preview`와 모의투자로 충분히 검증하세요. 현재 실주문은 여러 안전 조건을 모두 충족하기 전까지 자동으로 차단됩니다.

## 1. 이 프로그램이 하는 일

- TQQQ 또는 SOXL의 순수 V4 매수·매도 가격과 수량을 같은 입력에서 항상 똑같이 계산합니다.
- 주문 전 잔고, 주문가능금액, 기존 주문과 안전 한도를 확인합니다.
- 매도 LOC를 먼저 준비하고, 미국 정규장 시작 후 상태를 다시 확인한 다음 매수 LOC를 준비합니다.
- 주문·체결·부분체결·취소를 SQLite에 기록하고 프로그램을 다시 시작해도 이어서 복구합니다.
- 같은 명령을 반복해도 같은 주문이 중복 제출되지 않도록 막습니다.
- 미국 휴장일, 서머타임, 조기폐장일을 미국 거래소 일정으로 계산합니다.

다음 기능은 하지 않습니다.

- 종목 추천, 시장 예측, Hermes/LLM 투자 판단
- 손실을 막아주거나 수익을 보장하는 기능
- 사용자가 승인하지 않은 전략 변경
- 미확인 DB증권 기능을 추측해서 실주문하는 기능

## 2. 꼭 알아둘 용어

| 용어 | 쉬운 설명 |
|---|---|
| APP_KEY | DB증권에서 계좌별로 발급하는 API 사용자 ID와 비슷한 값 |
| APP_SECRET | APP_KEY와 짝을 이루는 비밀번호. 누구에게도 보여주면 안 됨 |
| Access Token | APP_KEY와 APP_SECRET으로 발급받는 24시간짜리 임시 출입증 |
| preview | 주문 계산 결과만 보여주는 기본 모드. DB증권 주문 없음 |
| paper | 프로그램 내부에서 주문 접수만 흉내 내는 모드 |
| live | 실제 DB증권 계좌에 주문하는 모드. 기본적으로 잠겨 있음 |
| LOC | 지정한 조건을 만족하면 정규장 종가로 체결시키는 주문 |
| T | V4 전략의 진행 정도를 나타내는 값 |
| 사이클 | 첫 매수부터 해당 보유 흐름이 끝날 때까지의 한 묶음 |

## 3. 시작 전에 준비할 것

1. Windows 11 컴퓨터
2. DB증권 계좌와 해외주식·해외 ETF 거래 신청
3. DB증권 Open API 사용 신청
4. 계좌별 APP_KEY와 APP_SECRET
5. PowerShell
6. Python 실행환경을 준비해 주는 `uv`

DB증권 공식 신청 순서는 [OPEN API 이용절차 안내](https://openapi.dbsec.co.kr/howto-use)를 확인하세요.

- DB증권 계좌가 있어야 합니다.
- 홈페이지 공동인증서 로그인 후 `온라인지점 > OpenAPI > OpenAPI 신청`으로 이동합니다.
- 최대 3계좌까지 신청할 수 있습니다.
- 모의투자용 APP_KEY와 APP_SECRET은 실계좌용과 별도로 발급됩니다.
- 개인 키 유효기간은 신청일부터 1년, 법인은 3개월입니다.
- Access Token은 24시간 동안 유효하며 프로그램이 필요할 때 다시 발급합니다.

> [!CAUTION]
> APP_KEY와 APP_SECRET을 README, `.env`, 이메일, 메신저, 화면 캡처, GitHub, AI 채팅에 붙여 넣지 마세요. 이 프로그램은 Windows 자격 증명 관리자에 저장합니다.

## 4. 가장 쉬운 설치 방법

PowerShell을 열고 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Users\hoyoung\Desktop\infinite-buying-dbapi
```

`uv`가 없다면 먼저 설치합니다. 설치가 어려우면 강사에게 `uv` 설치를 요청하세요.

```powershell
winget install --id=astral-sh.uv -e
```

프로젝트 전용 Python 3.12 환경과 필요한 패키지를 설치합니다.

```powershell
uv sync --python 3.12
```

정상 설치 확인:

```powershell
uv run app --help
```

명령 목록이 나오면 설치가 끝난 것입니다. 자세한 내용은 [설치 매뉴얼](docs/manuals/01-installation.md)을 참고하세요.

## 5. DB증권 키를 안전하게 등록하기

DB증권에서 내려받은 다음 형식은 `.env` 예제가 아니라 **발급 자격증명 JSON**입니다.

```json
{
  "appkey": "발급받은 값",
  "appsecret": "발급받은 값",
  "env": "real",
  "expire_date": "YYYYMMDD"
}
```

- `appkey`, `appsecret`: Access Token 발급에 사용하는 장기 자격증명
- `env=real`: 실계좌용 발급 묶음이라는 메타데이터
- `expire_date`: APP KEY·SECRET 만료일이며 24시간짜리 Access Token 만료일이 아님
- 네 필드 모두를 OAuth 요청에 보내는 것은 아닙니다.

다음 명령을 실행합니다.

```powershell
uv run app setup --account-alias student-001 --save-api-credentials
```

화면에 아래 질문이 차례로 나옵니다.

```text
DB Securities app key:
DB Securities app secret:
```

홈페이지에서 받은 값을 입력하세요. 입력 중 글자가 화면에 보이지 않는 것이 정상입니다.

- `student-001`은 계좌번호가 아니라 이 컴퓨터에서 사용할 별칭입니다.
- 수강생마다 다른 별칭, 다른 Windows 사용자, 다른 데이터베이스를 사용하세요.
- 프로그램은 APP_KEY와 APP_SECRET을 Windows 자격 증명 관리자에 저장합니다.

이미 `.env`에 `DB_APPKEY`, `DB_APPSECRET`, `DB_ENV`, `DB_EXPIRE_DATE`를 넣었다면 한 번만 가져올 수 있습니다.

```powershell
uv run app setup --account-alias student-001 --import-env-credentials
```

성공 후 `.env`에서 `DB_APPKEY`, `DB_APPSECRET` 줄을 삭제하세요. 이 네 이름은 DB증권 발급 JSON을 안전 저장소로 옮길 때 쓰는 입력이며, `IB_ENVIRONMENT=preview|paper|live` 같은 프로그램 운용 설정과는 다른 개념입니다.

### OAuth 요청 형식에 관한 중요 안내

2026-07-12 확인 기준으로 DB증권 홈페이지 이용절차와 다운로드형 OAuth 명세의 요청 형식이 서로 다릅니다.

| 자료 | Content-Type | Secret 필드 | 추가 필드 |
|---|---|---|---|
| 홈페이지 이용절차 | `application/json` | `appsecret` | 없음 |
| 다운로드 OAuth 명세 | `application/x-www-form-urlencoded` | `appsecretkey` | `scope=oob` |

공식 다운로드 명세, 공식 테스트베드 샘플, 2026-07-12 실계좌 키 인증 결과가 모두 다음 `form` 방식을 확인하므로 프로그램 기본값도 이에 맞췄습니다.

```text
IB_DBSEC_OAUTH_STYLE=form
```

홈페이지 이용절차의 JSON 예시는 참고용 호환 방식으로만 남겨 둡니다. 프로그램은 토큰 발급 제한 때문에 두 형식을 자동으로 연속 재시도하지 않습니다. 자세한 내용은 [DB증권 API 신청·인증 매뉴얼](docs/manuals/02-dbsec-api-setup.md)을 읽으세요.

## 6. 첫 전략 프로필 만들기

키 등록 후 다음 읽기 전용 명령으로 인증과 계좌·시세를 확인할 수 있습니다. 원본 JSON, 키, 토큰, 전체 계좌번호는 출력하지 않습니다.

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
uv run app dbsec transaction-history --start 2026-07-01 --end 2026-07-13
uv run app dbsec current-price --symbol TQQQ
uv run app dbsec daily-chart --symbol TQQQ --start 2026-07-01 --end 2026-07-13
```

실제 로컬 프로필을 대조할 때만 `uv run app reconcile p1 --environment live`를 사용합니다. 수량이 다르면 `RECONCILIATION_REQUIRED`로 전환되어 신규 주문이 차단됩니다.
공식 TR 제한값을 아직 설정하지 않은 읽기 전용 명령은 보수적으로 초당 1회만 호출합니다. live 대조와 주문에는 확인된 `IB_DBSEC_REQUESTS_PER_SECOND`가 계속 필요합니다.

처음에는 TQQQ 40분할을 권장합니다.

```powershell
uv run app profile create p1 --symbol TQQQ --division 40 --capital 10000
```

여기서 `--capital 10000`은 원화 1천만 원이 아니라 **미화 10,000달러**입니다.

지원 범위:

| 종목 | 분할수 | 상태 |
|---|---:|---|
| TQQQ, SOXL | 20 | preview·paper, 검증 후 live 후보 |
| TQQQ, SOXL | 30 | 실험용. preview·paper만 가능 |
| TQQQ, SOXL | 40 | preview·paper, 검증 후 live 후보 |

등록 확인:

```powershell
uv run app profile list
```

## 7. 주문 없이 첫 미리보기

아래 명령은 DB증권에 주문하지 않습니다.

```powershell
uv run app preview p1 --previous-close 100 --completed-closes 96,97,98,99,100
```

결과의 주요 항목:

- `side`: `BUY`는 매수, `SELL`은 매도
- `order_type`: LOC, LIMIT, MOC
- `quantity`: 주문 예정 주식 수
- `limit_price`: 주문 기준 가격
- `reason_code`: 이 주문을 만든 전략상의 이유
- `intent_id`: 중복 주문을 막는 고유 ID

이 단계에서 실제 주문은 절대 나가지 않습니다. [첫 미리보기 매뉴얼](docs/manuals/03-first-preview.md)에 결과 읽는 법이 있습니다.

## 8. 모의운영부터 시작하기

먼저 문서로 확인된 기능을 기록합니다.

```powershell
uv run app capability verify
```

그다음 paper 주문 흐름을 연습합니다.

```powershell
uv run app run sell-phase p1 --previous-close 100 --completed-closes 96,97,98,99,100 --environment paper
uv run app reconcile p1 --broker-quantity 0 --environment paper
uv run app run buy-phase p1 --previous-close 100 --completed-closes 96,97,98,99,100 --environment paper
uv run app orders list
```

DB증권 모의계좌에서는 [양방향 LOC 테스트베드 절차](docs/testbed-protocol.md)를 별도로 통과해야 합니다. 단순히 앱에 주문이 보이는 것만으로 성공 처리하지 않습니다.

## 9. 실주문이 쉽게 열리지 않는 이유

아래 조건 중 하나라도 빠지면 `live` 주문은 거부됩니다.

- TQQQ 또는 SOXL의 20/40분할 프로필
- 같은 종목 LOC 매도 후 LOC 매수 테스트 성공
- 사용하는 모든 DB증권 TR의 공식 호출 제한 확인
- 법률·배포 검토와 위험고지 확인
- 비상정지 해제
- 해당 거래일 운영자 승인
- DB증권 주문·체결·잔고와 로컬 상태 대조 성공
- 주문별·일별 최대 금액 이내

처음 설치한 날 바로 실주문을 켜지 마세요. 최소 20개 미국 거래일의 shadow 운영이 먼저입니다. 자세한 절차는 [모의·Shadow 운영](docs/manuals/04-paper-and-shadow.md)과 [실주문 운영](docs/manuals/05-live-operations.md)을 참고하세요.

## 10. 매일 확인할 순서

1. 비상정지 상태와 미국 거래일 여부 확인
2. DB증권 잔고·미체결 주문 대조
3. 프리마켓 초반 매도 단계 실행
4. 앱에서 주문 접수 확인
5. 정규장 초반 다시 대조
6. 매수 단계 실행
7. 체결·부분체결·거절 확인
8. 종료 전 진단보고서와 백업 생성

미국장 기준 시각 확인:

```powershell
uv run app scheduler show --session-date 2026-07-13
```

## 11. 문제가 생기면 가장 먼저 할 일

```powershell
uv run app emergency-stop on
```

그다음 상태를 확인합니다.

```powershell
uv run app orders list
uv run app diagnostics --output diagnostics/report.json --redacted
uv run app backup create backups/state-backup.sqlite3
```

- 주문 결과가 불명확하면 같은 주문을 다시 보내지 마세요.
- `RECONCILIATION_REQUIRED`가 나오면 새 주문을 중단하고 DB증권 앱의 잔고·미체결 주문과 비교하세요.
- SQLite 파일을 엑셀이나 DB 편집기로 직접 고치지 마세요.
- 진단보고서는 `--redacted` 옵션을 유지한 상태로만 전달하세요.

자세한 오류별 해결책은 [문제 해결 매뉴얼](docs/manuals/06-troubleshooting.md)에 있습니다.

## 12. 매뉴얼 목차

| 문서 | 언제 읽나요? |
|---|---|
| [전체 매뉴얼 인덱스](docs/manuals/README.md) | 모든 문서를 순서대로 보고 싶을 때 |
| [01. 설치](docs/manuals/01-installation.md) | 처음 설치하거나 PC를 바꿀 때 |
| [02. DB증권 신청과 인증](docs/manuals/02-dbsec-api-setup.md) | APP_KEY·APP_SECRET·토큰이 궁금할 때 |
| [03. 첫 미리보기](docs/manuals/03-first-preview.md) | 주문 없이 계산 결과를 확인할 때 |
| [04. 모의·Shadow 운영](docs/manuals/04-paper-and-shadow.md) | 실주문 전 검증할 때 |
| [05. 실주문 운영](docs/manuals/05-live-operations.md) | 모든 출시 조건을 통과한 뒤 운영할 때 |
| [06. 문제 해결](docs/manuals/06-troubleshooting.md) | 오류 메시지나 상태 불일치가 생겼을 때 |
| [07. 보안·백업·수강생별 분리](docs/manuals/07-security-and-backup.md) | 키 보관, 백업, 진단보고서가 궁금할 때 |
| [전략 규칙 원문](docs/ruleset-1.md) | V4 계산식과 부분체결 규칙을 확인할 때 |
| [DB증권 기능 매트릭스](docs/dbsec-capability-matrix.md) | 무엇이 확인됐고 무엇이 미확인인지 볼 때 |
| [구현 계약](docs/implementation-plan.md) | 개발자·유지보수 담당자가 구조를 볼 때 |

## 13. 개발자용 검사

일반 수강생은 실행하지 않아도 됩니다.

```powershell
uv sync --python 3.12 --extra dev
uv run ruff check .
uv run pytest --cov=infinite_buying_dbapi
uv build
```

현재 전략 버전은 `pure-v4-ruleset-1`, 프로그램 버전은 `0.1.0`입니다. 전략 규칙을 바꾸면 기존 이름을 덮어쓰지 말고 새 규칙 버전과 새 골든 테스트를 만들어야 합니다.
