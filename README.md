# 순수 무한매수 V4 + DB증권 자동매매

DB증권 Open API를 이용해 `순수 무한매수 V4` 규칙을 계산하고, 주문을 안전하게 준비·기록·대조하는 Windows/macOS용 프로그램입니다.

처음 사용하는 분은 이 README를 위에서부터 차례로 따라 하세요. 세부 설명은 [전체 매뉴얼 목차](docs/manuals/README.md)에 따로 정리되어 있습니다.

> [!WARNING]
> 이 프로그램은 투자 권유나 수익 보장 도구가 아닙니다. 레버리지 ETF는 큰 손실이 발생할 수 있습니다. `preview`로 계산을 확인하고 강사 실계좌 인수시험 증거가 등록되기 전에는 실주문이 자동으로 차단됩니다.

## 현재 배포 상태

| 항목 | 상태 |
|---|---|
| 프로그램 | `0.2.0` |
| 전략 | `pure-v4-ruleset-1` — 변경 없음 |
| 내장 날씨 | `regime-weather-1` — TQQQ/QQQ, SOXL/SMH, 공통 SPY |
| 계좌 모드 | DB증권 `real` 전용. 로컬 paper·가상체결 제거 |
| 새 프로필 | `OFF`, 비상정지 `ON` |
| 실계좌 읽기 전용 | OAuth·빈 잔고 실응답 확인. 거래내역·5종목 시세/일봉은 문서와 CLI 구현 완료, 실응답 추가 확인 필요 |
| 실주문 | 강사 계좌 1주 인수시험 증거가 등록될 때까지 fail-closed |
| Hermes 연동 | 저장소 안의 단일 진입 문서는 `docs/hermes-handoff.md`. 외부 연결은 실습에서 구성 |

Python 3.12 검사는 Windows와 macOS에서, 대시보드 검사는 Windows에서 [GitHub Actions](https://github.com/hotorch/infinite-buying-dbapi/actions)로 실행됩니다.

## 1. 이 프로그램이 하는 일

- TQQQ 또는 SOXL의 순수 V4 매수·매도 가격과 수량을 같은 입력에서 항상 똑같이 계산합니다.
- 주문 전 잔고, 주문가능금액, 기존 주문과 안전 한도를 확인합니다.
- 매도 LOC를 먼저 준비하고, 미국 정규장 시작 후 상태를 다시 확인한 다음 매수 LOC를 준비합니다.
- 주문·체결·부분체결·취소를 SQLite에 기록하고 프로그램을 다시 시작해도 이어서 복구합니다.
- 같은 명령을 반복해도 같은 주문이 중복 제출되지 않도록 막습니다.
- 미국 휴장일, 서머타임, 조기폐장일을 미국 거래소 일정으로 계산합니다.
- TQQQ/SOXL에 `regime-weather-1` 날씨 엔진을 적용하고 회차·거래일차·자금 이벤트를 보여줍니다. 날씨는 설명과 보고에만 쓰며 주문이나 자금 배분을 바꾸지 않습니다.
- Windows/macOS에서 `app dashboard start`로 백테스트·날씨·회차 대시보드를 실행합니다.

다음 기능은 하지 않습니다.

- 종목 추천, 시장 예측, Hermes/LLM의 전략 가격·수량·`T` 변경
- 날씨나 LLM 의견을 이용한 자동 자금 배분
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
| fail-closed | 안전 조건이 하나라도 불확실하면 주문을 허용하지 않는 방식 |
| capability | DB증권 기능이 공식 문서나 실계좌 시험으로 확인됐는지 나타내는 안전 근거 |
| readiness | 프로필을 ON으로 만들기 전에 모든 안전 조건을 모아 검사한 결과 |
| OFF / ON / LOCKED | 신규 주문 차단 / 자동실행 허용 / 기계적 불확실성으로 잠김 |
| LOC | 지정한 조건을 만족하면 정규장 종가로 체결시키는 주문 |
| T | V4 전략의 진행 정도를 나타내는 값 |
| 사이클 | 첫 매수부터 해당 보유 흐름이 끝날 때까지의 한 묶음 |
| intent / outbox | 계산된 주문 계획 / 중복 제출을 막기 위해 그 계획을 보관하는 로컬 기록 |
| reconciliation(대사) | DB증권의 실제 보유·주문과 로컬 기록이 같은지 비교하는 절차 |
| fixture | 비밀값을 제거하고 테스트용으로 고정해 둔 API 응답 예시 |

## 3. 시작 전에 준비할 것

1. Windows 11 또는 최신 macOS 컴퓨터
2. DB증권 계좌와 해외주식·해외 ETF 거래 신청
3. DB증권 Open API 사용 신청
4. 계좌별 APP_KEY와 APP_SECRET
5. Windows는 PowerShell, macOS는 Terminal
6. Python 실행환경을 준비해 주는 `uv`

### 돈이 필요한 시점

- API 인증, 빈 잔고·보유·거래내역, 현재가·일봉 조회는 계좌 잔고가 0이어도 됩니다.
- `preview`, 백테스트, 대시보드는 실제 돈을 사용하지 않습니다.
- `automation readiness`, 프로필 `ON`, 1주 실계좌 인수시험에는 **결제완료된 주문가능 USD**가 필요합니다. 원화 입금만 된 상태나 결제 예정 금액은 사용할 수 없습니다.
- 프로필 배정자금은 실제 계좌 총액과 결제완료 USD를 넘기지 않게 정하세요. 테스트 목적이라도 임의로 capability를 `확인됨` 처리하면 안 됩니다.

DB증권 공식 신청 순서는 [OPEN API 이용절차 안내](https://openapi.dbsec.co.kr/howto-use)를 확인하세요.

- DB증권 계좌가 있어야 합니다.
- 홈페이지 공동인증서 로그인 후 `온라인지점 > OpenAPI > OpenAPI 신청`으로 이동합니다.
- 최대 3계좌까지 신청할 수 있습니다.
- 모의투자용 APP_KEY와 APP_SECRET은 실계좌용과 별도로 발급됩니다.
- 개인 키 유효기간은 신청일부터 1년, 법인은 3개월입니다.
- Access Token은 24시간 동안 유효하며 프로그램이 필요할 때 다시 발급합니다.

> [!CAUTION]
> APP_KEY와 APP_SECRET을 README, `.env`, 이메일, 메신저, 화면 캡처, GitHub, AI 채팅에 붙여 넣지 마세요. 이 프로그램은 Windows Credential Manager 또는 macOS Keychain에 저장합니다.

## 4. 가장 쉬운 설치 방법

아래 첫 예시는 Windows용입니다. macOS에서는 [공식 uv 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)에 따라 `uv`를 설치한 뒤 Terminal에서 프로젝트 폴더로 이동하세요. 그다음 `uv sync`와 `uv run app --help`는 두 운영체제에서 같습니다.

PowerShell을 열고 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Users\student\Desktop\infinite-buying-dbapi
```

`student`를 포함한 경로 전체를 자신의 실제 프로젝트 위치로 바꾸세요. 탐색기에서 프로젝트 폴더를 연 뒤 주소 표시줄의 경로를 복사해도 됩니다.

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

먼저 자격증명과 로컬 DB만 초기화합니다. 이 단계에서는 프로필을 만들거나 주문하지 않습니다.

```powershell
uv run app setup --account-alias student-001 --save-api-credentials --credential-expire-date YYYYMMDD
```

화면에 아래 질문이 차례로 나옵니다.

```text
DB Securities app key:
DB Securities app secret:
```

홈페이지에서 받은 값을 입력하세요. 입력 중 글자가 화면에 보이지 않는 것이 정상입니다.

- `student-001`은 계좌번호가 아니라 이 컴퓨터에서 사용할 별칭입니다.
- 수강생마다 다른 별칭, 다른 Windows 사용자, 다른 데이터베이스를 사용하세요.
- 프로그램은 APP_KEY와 APP_SECRET을 OS keychain에 저장합니다.

이미 `.env`에 `DB_APPKEY`, `DB_APPSECRET`, `DB_ENV`, `DB_EXPIRE_DATE`를 넣었다면 한 번만 가져올 수 있습니다.

```powershell
uv run app setup --account-alias student-001 --import-env-credentials
```

성공 후 `.env`에서 `DB_APPKEY`, `DB_APPSECRET` 줄을 삭제하세요. 계좌 모드는 `IB_DBSEC_ACCOUNT_MODE=real`이 기본입니다. 제거된 `IB_ENVIRONMENT`가 남아 있으면 0.2.0은 마이그레이션 오류로 중단합니다.

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

## 6. 계좌를 조회하고 첫 프로필 만들기

키 등록 후 다음 읽기 전용 명령으로 인증과 계좌·시세를 확인할 수 있습니다. 원본 JSON, 키, 토큰, 전체 계좌번호는 출력하지 않습니다.

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
uv run app dbsec transaction-history --start 2026-07-01 --end 2026-07-13
uv run app dbsec current-price --symbol TQQQ
uv run app dbsec daily-chart --symbol TQQQ --start 2026-07-01 --end 2026-07-13
```

잔고가 0이면 `balance_rows=0`, `holdings=0`, `transactions=0`이 정상 결과입니다. 조회 단계에서는 입금하지 않아도 됩니다.

실제 로컬 프로필을 만든 뒤 대조할 때만 `uv run app reconcile --profile tqqq --json`을 사용합니다. 수량이 다르면 `LOCKED + RECONCILIATION_REQUIRED`로 전환되어 신규 주문이 차단됩니다.
공식 TR 제한값을 아직 설정하지 않은 읽기 전용 명령은 보수적으로 초당 1회만 호출합니다. 실계좌 대조와 주문에는 공식 근거로 확인한 `IB_DBSEC_REQUESTS_PER_SECOND`가 필요합니다.

수업에서 정한 종목·분할수·실제 배정 USD에 맞춰 프로필을 하나씩 만듭니다. 같은 계좌에서 같은 종목을 여러 프로필이 소유할 수 없습니다.

```powershell
uv run app profile create tqqq --symbol TQQQ --division 40 --capital 10000
```

여기서 `--capital 10000`은 원화 1천만 원이 아니라 **미화 10,000달러**입니다.

지원 범위:

| 종목 | 분할수 | 상태 |
|---|---:|---|
| TQQQ, SOXL | 20 | preview, 검증 후 실주문 후보 |
| TQQQ, SOXL | 30 | 백테스트·preview 전용 |
| TQQQ, SOXL | 40 | preview, 검증 후 실주문 후보 |

등록 확인:

```powershell
uv run app profile list
```

설치와 프로필 생성을 한 번에 하려면 5절의 `setup` 명령에 필요한 프로필 옵션만 추가할 수 있습니다. 아래 명령은 `tqqq`라는 OFF 프로필을 함께 만듭니다.

```powershell
uv run app setup --account-alias student-001 --save-api-credentials --credential-expire-date YYYYMMDD --tqqq-capital 10000 --tqqq-division 40
```

이 방법을 사용했다면 `profile create tqqq ...`를 다시 실행하지 마세요.

## 7. 주문 없이 첫 미리보기

아래 명령은 DB증권에 주문하지 않습니다.

```powershell
uv run app preview tqqq --previous-close 100 --completed-closes 96,97,98,99,100
```

결과의 주요 항목:

- `side`: `BUY`는 매수, `SELL`은 매도
- `order_type`: LOC, LIMIT, MOC
- `quantity`: 주문 예정 주식 수
- `limit_price`: 주문 기준 가격
- `reason_code`: 이 주문을 만든 전략상의 이유
- `intent_id`: 중복 주문을 막는 고유 ID

이 단계에서 실제 주문은 절대 나가지 않습니다. [첫 미리보기 매뉴얼](docs/manuals/03-first-preview.md)에 결과 읽는 법이 있습니다.

## 8. 실주문 준비 확인

먼저 문서로 확인된 기능을 기록합니다.

```powershell
uv run app capability verify
```

`preview`는 상태, outbox, 주문을 전혀 기록하지 않는 계산 전용 명령입니다. 실주문 준비 상태는 다음 JSON으로 확인합니다.

```powershell
uv run app weather update --symbol TQQQ --json
uv run app automation readiness --profile tqqq
uv run app automation status tqqq --json
```

강사 실계좌에서는 [최소수량 실계좌 테스트베드 절차](docs/testbed-protocol.md)를 별도로 통과해야 합니다. 증거가 capability matrix에 등록되기 전에는 ON이 되지 않습니다.

## 9. 실주문이 쉽게 열리지 않는 이유

아래 조건 중 하나라도 빠지면 실주문은 거부됩니다.

- TQQQ 또는 SOXL의 20/40분할 프로필
- 같은 종목 LOC 매도 후 LOC 매수 테스트 성공
- 사용하는 모든 DB증권 TR의 공식 호출 제한 확인
- 비상정지 해제
- 사용자가 Hermes 외부 실행환경 준비 완료를 확인
- DB증권 주문·체결·잔고와 로컬 상태 대조 성공
- 최신 내장 날씨와 결제완료 USD 확인
- 강사 실계좌 LOC/LIMIT/MOC·취소·부분체결·timeout 대사 증거

Hermes에게 프로젝트를 설명할 때는 [Hermes 프로젝트 핸드오프](docs/hermes-handoff.md)를 첫 진입 문서로 지정하세요. 저장소에 접근할 수 있는 Hermes는 `AGENTS.md`와 핸드오프가 가리키는 원문도 함께 읽어야 합니다. 실제 운영은 [실주문 운영](docs/manuals/05-live-operations.md)을 참고하세요.

## 10. Hermes에게 프로젝트 알려주기

Hermes는 저장소 루트의 `AGENTS.md`를 확인한 뒤 [`docs/hermes-handoff.md`](docs/hermes-handoff.md)를 읽어야 합니다. 핸드오프는 V4의 사전 맥락, 핵심 용어, 정상·리버스 흐름, 부분체결과 `T`, 숙지 체크리스트, 안전한 CLI 사용법, 장애 대응 순서를 연결하는 단일 진입 문서입니다. 파일 하나만 저장소 밖으로 복사한 경우에는 원문과 코드를 대조할 수 없으므로 상태 변경이나 실계좌 명령을 실행하면 안 됩니다.

Hermes는 기본적으로 조회와 설명만 합니다. Hermes의 시장 의견은 주문 가격·수량·`T`·자금 배분을 바꿀 수 없습니다. 상태 변경 명령은 사용자가 정확한 명령과 대상을 명시한 경우에만 실행할 수 있습니다. 반복 `automation tick`은 사용자가 고정 일정을 별도로 구성하고 대상 프로필을 명시적으로 ON으로 만든 경우에만 허용됩니다.

이 저장소는 Hermes skill, 실행 wrapper, 일정, Slack, Gateway 설정을 제공하지 않습니다. 외부 자동화는 사용자가 별도로 구성하며, 프로젝트 조작에는 핸드오프에 적힌 `uv run app ...` 공개 CLI만 사용합니다.

안전한 조회 명령:

```powershell
uv run app automation status --json
uv run app report daily --session-date latest --json
uv run app position status tqqq --json
uv run app position cycles tqqq --json
uv run app orders list --profile tqqq --json
uv run app weather current --symbol TQQQ --json
uv run app capital status
```

> [!CAUTION]
> 위 조회 목록과 `uv run app ... --help` 이외의 명령은 기본적으로 상태·프로세스·파일을 변경할 수 있습니다. Hermes는 사용자가 정확한 명령과 대상을 명시한 경우에만 실행해야 합니다.

특히 다음 명령은 실계좌나 핵심 안전 상태에 직접 영향을 줄 수 있습니다.

| 명령 | 실제 영향 |
|---|---|
| `run sell-phase`, `run buy-phase` | 모든 게이트 통과 시 실제 주문 제출 가능 |
| `automation tick` | ON 프로필에서 실제 주문 단계 실행 가능 |
| `orders cancel`, `automation off` | DB증권 미체결 주문 취소 가능 |
| `automation on`, `emergency-stop off` | 신규 주문을 허용하는 상태로 변경 가능 |
| `capability verify` | 실주문 안전 게이트에 쓰는 증거 상태 변경 |
| `reconcile` | DB증권 조회 결과에 따라 로컬 대사·잠금 상태 변경 |
| `capital propose/apply/scan` | 자금 관련 로컬 상태 생성·변경 가능 |
| `backup restore` | 활성 SQLite 상태 교체 |

`setup`, `profile create`, `weather update`, `emergency-stop on`, `backup create`, `diagnostics`, `dashboard start`도 주문 제출 명령은 아니지만 로컬 상태·파일·프로세스를 변경하므로 사용자 요청 없이 실행하지 않습니다.

`capital scan`은 DB증권 입출금·환전·결제내역 capability와 공식 응답 fixture가 확인되기 전까지 의도적으로 차단됩니다.

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
- `UNKNOWN`, `LOCKED`, `RECONCILIATION_REQUIRED`가 나오면 새 주문을 중단하고 DB증권 앱의 잔고·미체결 주문과 비교하세요.
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
| [04. Hermes 프로젝트 핸드오프](docs/hermes-handoff.md) | Hermes에게 무한매수 배경지식·사용법·상대경로를 전달할 때 |
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

현재 전략 버전은 `pure-v4-ruleset-1`, 날씨 버전은 `regime-weather-1`, 프로그램 버전은 `0.2.0`입니다. 전략 규칙을 바꾸면 기존 이름을 덮어쓰지 말고 새 규칙 버전과 새 골든 테스트를 만들어야 합니다.
