# Hermes 프로젝트 핸드오프

이 문서는 Hermes에게 이 프로젝트를 설명하는 **유일한 온보딩 문서**다. Hermes는 필요하면 자신의 환경에서 skill과 자동화 방법을 직접 구성한다. 이 저장소는 Hermes용 skill, 실행 wrapper, cron 정의, Slack 설정, Gateway 설정을 제공하지 않는다.

모든 경로는 저장소 루트 기준 상대경로다.

## 1. 프로젝트의 목적

이 프로젝트는 TQQQ와 SOXL에 `순수 무한매수 V4`를 적용하는 Python 3.12 CLI다. 전략 계산은 결정적이며, DB증권 실계좌 주문은 capability·자격증명·잔고·대사·최신 데이터 검사를 모두 통과해야만 열린다.

- 앱 버전: `0.2.x`
- 전략 버전: `pure-v4-ruleset-1`
- 날씨 버전: `regime-weather-1`
- CLI: `uv run app ...`
- 로컬 상태: SQLite. 직접 열거나 수정하지 않는다.
- 비밀값: OS keychain에만 저장한다. 출력·문서·메시지에 복사하지 않는다.

## 2. 무한매수 배경지식

무한매수는 자금을 여러 분할로 나누어 한 번에 모두 투입하지 않고, 보유 상태와 평균단가에 따라 매수·매도를 반복하는 운용 개념이다. 이 프로젝트의 V4는 일반적인 설명을 임의 해석하지 않고 `docs/ruleset-1.md`에 고정된 수식만 사용한다.

Hermes가 알아야 할 핵심은 다음과 같다.

1. `division_count`는 전체 전략 자금을 몇 단계로 나누는지 나타낸다. 실주문 후보는 20/40분할이고, 30분할은 preview·백테스트 전용이다.
2. `T`는 거래일 수가 아니라 전략 진행값이다. 부분체결이면 체결 비율만큼 소수 단위로 변한다.
3. 첫 BUY 체결이 한 회차를 열고, 수량을 0으로 만드는 SELL 체결이 회차를 닫는다. 같은 시각의 체결은 SELL 후 BUY 순서라서 청산 직후 BUY는 새 회차다.
4. 정상 모드에서는 이전 종가·평균단가·`T`·남은 현금으로 주문 가격과 수량을 계산한다. Hermes가 가격·수량·`T`를 바꾸지 않는다.
5. `T > division_count - 1`이면 역방향 모드에 들어갈 수 있다. 진입·매수·매도·정상 복귀 규칙도 `docs/ruleset-1.md`에 고정되어 있다.
6. 날씨는 TQQQ에 QQQ, SOXL에 SMH, 공통으로 SPY를 사용한다. 날씨는 설명과 신규 결제완료 USD 배분에만 쓰고 진행 중인 V4 주문을 바꾸지 않는다.
7. `OFF`는 신규 주문 차단, `ON`은 자동 실행 허용, `LOCKED`는 UNKNOWN 주문이나 대사 불일치 같은 기계적 불확실성이다. `LOCKED`를 임의 해제하지 않는다.

전략을 설명하거나 판단하기 전에는 반드시 `docs/ruleset-1.md`를 읽는다. 코드와 문서가 다르면 주문하지 말고 차이를 보고한다.

## 3. 상대경로 지도

| 상대경로 | 용도 |
|---|---|
| `README.md` | 설치, 자격증명 등록, 프로필 생성, preview의 사용자 안내 |
| `docs/ruleset-1.md` | Pure V4 수식·체결 전이·역방향 모드의 기준 문서 |
| `docs/operations.md` | 운영자가 사용할 CLI 요약 |
| `docs/testbed-protocol.md` | 실계좌 최소수량 인수시험과 증거 수집 절차 |
| `docs/dbsec-capability-matrix.md` | 확인된 DB증권 기능과 아직 차단된 기능 |
| `docs/manuals/05-live-operations.md` | ON/OFF·대사 중심의 실주문 운영 절차 |
| `src/infinite_buying_dbapi/strategy.py` | 외부 의존성이 없는 결정적 전략 계산 코어 |
| `src/infinite_buying_dbapi/models.py` | 전략·주문·체결·프로필 도메인 계약 |
| `src/infinite_buying_dbapi/cli.py` | 공개 CLI 명령과 JSON 계약의 구현 |
| `data/market/metadata.json` | 배포 시장 데이터의 범위와 SHA-256 |

Hermes는 위 경로를 읽을 수 있지만 소스, 환경변수, SQLite, 시장 데이터, broker payload를 수정하지 않는다.

## 4. 프로젝트 사용법

저장소 루트에서 명령을 실행한다. 먼저 공개 명령을 확인한다.

```powershell
uv sync --python 3.12
uv run app --help
```

### 읽기 전용 점검

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
uv run app automation status --json
uv run app position status --json
uv run app orders list --json
uv run app capital status
```

잔고·보유·거래내역이 없는 새 계좌에서는 0건이 정상이다.

### 전략과 날씨 확인

```powershell
uv run app preview PROFILE --previous-close PRICE --completed-closes P1,P2,P3,P4,P5
uv run app weather update --symbol TQQQ --json
uv run app weather current --symbol TQQQ --json
uv run app weather history --symbol TQQQ --limit 20 --json
```

SOXL은 `--symbol SOXL`을 사용한다. `preview`는 주문·outbox·전략 상태를 기록하지 않는다.

### 회차·주문·보고 조회

```powershell
uv run app position status PROFILE --json
uv run app position cycles PROFILE --json
uv run app position sessions PROFILE --cycle N --json
uv run app orders list --profile PROFILE --json
uv run app report daily --session-date latest --json
```

### ON/OFF와 대사

```powershell
uv run app automation readiness --profile PROFILE
uv run app automation off --profile PROFILE
uv run app reconcile --profile PROFILE --json
```

ON 전환은 사용자가 외부 실습 준비가 끝났다고 명시하고 readiness의 모든 항목이 통과한 경우에만 `uv run app automation on --help`에서 현재 계약을 확인한 뒤 수행한다. 이 문서는 외부 실행환경을 정의하거나 대신 구성하지 않는다.

OFF는 신규 주문을 먼저 차단한 뒤 미체결을 취소·재조회한다. 결과가 불명확하면 `LOCKED + reconciliation_required`로 남겨야 하며 같은 주문이나 취소를 반복하지 않는다.

`capital scan`은 DB증권 입출금·환전·결제내역 capability와 공식 fixture가 확인되기 전까지 실패하는 것이 정상이다. 결과를 추측하거나 SQLite에 자금 이벤트를 만들지 않는다.

## 5. JSON과 실패 처리

공개 JSON 명령은 `schema_version`, `ok`, `data`, `warnings`, `errors`, `generated_at` envelope를 사용한다.

- `ok=false` 또는 nonzero 종료면 오류를 그대로 보고하고 자동 재시도하지 않는다.
- timeout, network, HTTP 5xx, 비정상 주문 JSON은 체결 실패가 아니라 `UNKNOWN` 가능성이다. 재주문하지 않고 대사한다.
- 주문·체결·현금·날씨는 JSON에 반환된 값만 설명한다. 보이지 않는 상태를 추론하지 않는다.
- 코드 변경이 필요하면 먼저 모든 프로필을 OFF로 만들고 미체결 0건과 대사 성공을 확인한 뒤 별도 개발 절차로 넘긴다.

## 6. 이 문서의 범위 밖

다음 항목은 사용자가 별도 실습에서 Hermes와 직접 구성한다. 이 저장소와 이 문서는 값, 일정, 채널, 전달 방식 또는 설치 절차를 정하지 않는다.

- Hermes skill 생성·설치
- cron 및 기타 실행 일정
- Slack 연결과 메시지 전달
- Hermes Gateway 설정

Hermes는 외부 구성을 완료한 뒤에도 이 프로젝트를 조작할 때 위 상대경로의 문서와 `uv run app ...` 공개 CLI만 사용한다.
