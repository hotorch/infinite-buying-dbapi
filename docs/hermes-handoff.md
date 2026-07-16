# Hermes 프로젝트 핸드오프

이 문서는 Hermes가 이 프로젝트를 처음 이해할 때 읽는 시작 문서다. 경로는 모두 저장소 루트 기준이다.

이 저장소는 Hermes용 skill, 실행 wrapper, cron 일정, Slack 연결, Gateway 설정을 제공하지 않는다. 그런 외부 연결은 사용자가 별도로 구성한다.

## 1. 먼저 기억할 세 가지

1. **Hermes가 투자 판단을 하지 않는다.** 종목, 가격, 수량, 분할수, `T`를 추천하거나 바꾸지 않는다.
2. **불확실하면 주문하지 않는다.** timeout, 네트워크 오류, 비정상 응답은 실패가 아니라 `UNKNOWN`일 수 있다. 같은 주문을 다시 보내지 않는다.
3. **SQLite와 비밀값을 직접 만지지 않는다.** 상태 확인과 조작에는 문서에 적힌 `uv run app ...` 명령만 사용한다.

## 2. 현재 버전과 역할

| 항목 | 현재 값 |
|---|---|
| 앱 | `0.2.0` |
| 전략 | `pure-v4-ruleset-1` |
| 날씨 | `regime-weather-1` |
| 지원 종목 | TQQQ, SOXL |
| 지원 분할 | 20, 30, 40 |
| 실주문 후보 | 20, 40만 가능 |
| 실행 방법 | `uv run app ...` |
| 로컬 상태 | SQLite, 직접 열거나 수정하지 않음 |
| 비밀값 | OS keychain에만 저장 |

이 프로그램은 같은 입력이면 같은 V4 결과를 만든다. DB증권 실주문은 자격증명, capability, 최신 데이터, 잔고, 주문가능금액, 대사, 비상정지 같은 모든 안전 조건을 통과해야만 가능하다.

## 3. Hermes가 할 수 있는 일

Hermes의 기본 역할은 **조회와 설명**이다.

- 프로필, 회차, 주문, 날씨, 자금 상태를 조회한다.
- CLI가 반환한 값을 쉬운 말로 설명한다.
- 오류가 나면 오류 코드와 다음 안전 조치를 알려준다.
- 코드나 문서가 서로 다르면 주문하지 않고 차이를 보고한다.

Hermes의 시장 의견이나 advisory proposal은 데이터일 뿐이다. 전략 상태, 주문 가격·수량, `T`, broker payload를 바꿀 수 없다.

상태를 바꾸거나 실계좌에 영향을 주는 명령은 Hermes가 스스로 판단해 실행하지 않는다. 사용자가 **정확한 명령과 대상을 명시적으로 지시한 경우에만** 그 명령을 기계적으로 실행할 수 있다. 반복 `automation tick`은 사용자가 고정 일정을 별도로 구성하고 대상 프로필을 명시적으로 ON으로 만든 경우에만 그 승인 범위 안에서 실행한다.

## 4. 무한매수 V4의 사전 맥락

무한매수 V4는 시장을 예측하는 모델이 아니다. 사용자가 미리 정한 종목과 자금을 여러 몫으로 나누고, 현재 보유상태·평균단가·진행값 `T`에 따라 다음 매수·매도 주문을 같은 공식으로 계산하는 **상태 기반 규칙**이다.

핵심 목적은 한 번에 모든 자금을 투입하는 대신 여러 단계로 나누어 운용하고, 보유 중에는 정해진 가격대에 분할 매수와 분할 매도를 반복하는 것이다. 이름에 “무한”이 들어가지만 자금이 무한하다는 뜻은 아니다. 남은 현금과 분할수 안에서만 계산한다.

이 전략은 손실을 막거나 수익을 보장하지 않는다. TQQQ와 SOXL은 레버리지 ETF이므로 큰 손실이 날 수 있다. Hermes는 V4를 투자 추천이나 시장 전망으로 설명하지 않는다.

프로그램의 전체 흐름은 다음 한 줄로 이해하면 된다.

```text
프로필 + 현재 전략 상태 + 완료된 시장 데이터
→ 순수 V4 계산
→ 주문 의도(intent)
→ 안전 게이트를 통과한 경우에만 DB증권 제출
→ 확인된 체결(fill)
→ 수량·현금·평균단가·T가 바뀐 새 상태
→ DB증권과 로컬 상태 대사
```

주문 의도를 만들었다고 체결된 것은 아니다. **확인된 체결만** 전략 상태를 바꾼다.

## 5. 먼저 알아야 할 용어

| 용어 | 쉬운 뜻 |
|---|---|
| 프로필 | 계좌 별칭, 종목, 분할수, 전략 자금을 묶은 설정 |
| `capital` | 사용자가 해당 프로필에 배정한 전체 전략 자금(USD) |
| `cash` | 전략 안에서 아직 사용하지 않은 남은 현금 |
| `quantity` | 현재 보유수량 |
| `average_cost` / `avg_cost` | 현재 보유분의 평균단가 |
| `division_count` | 전략 자금을 몇 단계로 나눌지 나타내는 20·30·40 중 하나 |
| `T` | 전략 진행값. 거래일 수가 아니며 부분체결 때문에 소수가 될 수 있음 |
| 회차(cycle) | 첫 BUY 체결부터 보유수량이 다시 0이 될 때까지의 한 묶음 |
| 세션(session) | 미국 거래소의 한 거래일 |
| 이전 종가 | 가장 최근에 완료된 공식 거래 세션의 종가 |
| 완료 종가 목록 | 리버스 계산에 쓰는 최근 최대 5개의 완료된 종가 |
| 별값(star price) | 평균단가와 현재 `T`로 계산하는 V4 기준 가격 |
| 목표가(target price) | 평균단가에 종목별 목표율을 더한 정상 모드 매도 가격 |
| 주문 의도(intent) | 전략이 계산한 주문 계획. 아직 주문이나 체결 자체는 아님 |
| 체결(fill) | DB증권에서 실제로 체결이 확인된 수량과 가격 |
| LOC | 지정한 제한가격 조건을 둔 종가 주문 |
| LIMIT | 지정가 주문 |
| MOC | 종가 시장가 주문 |
| 대사(reconciliation) | DB증권의 실제 보유·주문과 로컬 기록이 같은지 비교하는 절차 |

30분할은 preview와 백테스트만 가능하다. 20분할과 40분할만 모든 검증을 통과한 뒤 실주문 후보가 될 수 있다.

## 6. `T`를 정확히 이해하기

`T`는 “며칠째인가?”가 아니라 “계획한 매수·매도 단계가 체결 기준으로 얼마나 진행됐는가?”를 나타낸다.

- 최초 매수가 전부 체결되면 보통 `T`가 1 증가한다.
- 정상 매수가 계획의 절반만 체결되면 계획된 `T` 변화도 절반만 반영한다.
- 매도 체결은 매도 역할과 체결 비율에 따라 `T`를 비율로 줄인다.
- 주문이 접수됐지만 체결되지 않았다면 `T`는 바뀌지 않는다.

예를 들어 정상 모드의 한 몫 매수 10주가 `T + 1`로 계획됐는데 4주만 체결되었다면 체결 비율은 `4 / 10 = 0.4`이고, `T`는 0.4만 증가한다.

별값은 다음 규칙으로 계산한다.

```text
star_pct   = target_pct - (target_pct × 2 / division_count) × T
star_price = average_cost × (1 + star_pct)
```

종목별 목표율은 TQQQ 15%, SOXL 20%다. `T`가 변하면 별값도 변한다. Hermes가 이 값을 임의로 반올림하거나 수정하지 않는다.

## 7. 정상 모드의 흐름

### 보유수량이 0일 때

- 전략 자금의 `1 / division_count`를 최초 매수 예산으로 잡는다.
- LOC 제한가격은 이전 완료 종가의 120%다.
- 이는 `pure-v4-ruleset-1`에 고정한 선택이며 시장 전망값이 아니다.
- 1주도 살 수 없으면 0주 주문을 억지로 만들지 않는다.

### 보유 중 매수

한 번의 동적 매수 몫은 다음처럼 계산한다.

```text
남은 현금 / (division_count - T)
```

분모가 1 이하이면 정상 매수를 만들지 않는다.

- 전반부(`T < division_count / 2`): 한 몫을 절반씩 나누어 평균단가 LOC와 별값 아래 LOC에 둔다.
- 후반부: 한 몫 전부를 별값 아래 LOC에 둔다.
- 정수 주식만 주문하므로 예산을 나눈 뒤 남는 소액 때문에 별도 추가 주문을 만들지 않는다.

### 보유 중 매도

- 보유수량의 약 1/4을 별값 LOC로 계획한다. 최소 1주다.
- 나머지는 목표가 LIMIT로 계획한다.
- 목표가는 평균단가 대비 TQQQ 15%, SOXL 20%다.
- 두 매도수량의 합은 현재 보유수량을 넘지 않는다.

## 8. 매도 단계와 매수 단계

한 거래 세션에서는 매도 계획을 먼저 만들고, 이후 매수 계획을 만든다. 이 순서는 같은 종목에서 매도와 매수가 함께 존재할 수 있기 때문에 중요하다.

1. SELL 단계에서 현재 보유수량 안의 매도 의도를 계산한다.
2. DB증권 상태와 안전 조건을 다시 확인한다.
3. BUY 단계에서 남은 현금과 최신 상태로 매수 의도를 계산한다.
4. 체결이 확인되면 체결 역할과 비율에 따라 상태를 갱신한다.
5. DB증권과 로컬 상태를 대사한다.

같은 시각의 체결은 SELL을 먼저, BUY를 나중에 적용한다. SELL로 보유수량이 0이 된 뒤 같은 시각의 BUY가 체결되면 이전 회차를 닫고 새 회차를 연다.

## 9. 리버스 모드의 의미

`T > division_count - 1`이고 보유수량이 남아 있으면 정상 분할 단계가 거의 소진된 상태이므로 리버스 모드에 들어갈 수 있다. 리버스는 Hermes가 판단해 켜는 비상 버튼이 아니라 규칙이 상태에서 자동으로 계산하는 모드다.

- 진입할 때 남은 현금을 `reverse_cash_pool`로 고정한다.
- 리버스 첫 세션에는 보유수량의 `2 / division_count`에 해당하는 수량을 최소 1주 MOC로 매도하고 매수하지 않는다.
- 다음 세션부터 최근 최대 5개 완료 종가의 평균을 리버스 별값으로 사용한다.
- 이후에는 리버스 별값 LOC 매도와 그 아래 LOC 매수를 계산할 수 있다.
- 한 번의 리버스 매수는 진입 시 현금 풀의 1/4을 넘지 않는다.
- 이미 쓴 리버스 현금은 다시 쓸 수 없다.
- 다음 세션의 이전 종가가 평균단가의 85%보다 높으면 TQQQ가, 80%보다 높으면 SOXL이 정상 모드로 돌아갈 수 있다.

리버스 모드도 손실 회복을 보장하지 않는다. 조건과 수식을 임의로 완화하거나 강화하지 않는다.

## 10. 부분체결과 회차 전이

부분체결은 주문 전체가 아니라 실제 체결된 비율만 상태에 반영한다.

- 정상 BUY: 계획된 `T` 증가량 × 체결비율만큼 증가
- 별값 1/4 SELL: `T × (1 - 0.25 × 체결비율)`
- 목표가 SELL: `T × (1 - 0.75 × 체결비율)`
- 리버스 SELL: `T × (1 - (2 / division_count) × 체결비율)`
- 리버스 BUY: 남은 진행거리의 1/4 × 체결비율만큼 증가

회차 규칙은 다음과 같다.

- 첫 BUY 체결이 회차를 연다.
- SELL 체결로 수량이 0이 되면 회차를 닫는다.
- 미체결 주문만으로 회차를 열거나 닫지 않는다.
- 같은 시각에는 SELL 후 BUY 순서다.

Hermes는 요청수량과 체결수량을 혼동하지 않고, 부분체결을 전부 체결로 설명하지 않는다.

## 11. Hermes 숙지 체크리스트

Hermes는 전략을 설명하거나 운영 상태를 판단하기 전에 다음 내용을 답할 수 있어야 한다.

- `T`가 거래일 수가 아닌 이유는 무엇인가?
- 주문 의도와 실제 체결은 어떻게 다른가?
- 정상 모드의 전반부와 후반부 매수는 어떻게 다른가?
- 별값 매도와 목표가 매도는 수량과 가격이 어떻게 다른가?
- 리버스 모드는 언제 들어가며 첫날에는 왜 매수가 없는가?
- 부분체결이면 `T`가 왜 소수로 변하는가?
- 언제 한 회차가 열리고 닫히는가?
- 날씨와 Hermes 의견이 주문을 바꿀 수 없는 이유는 무엇인가?
- `UNKNOWN` 주문을 다시 보내면 안 되는 이유는 무엇인가?

정확한 계산이나 예외가 필요하면 `docs/ruleset-1.md`를 다시 읽고, 코드와 다르면 주문하지 말고 차이를 보고한다.

## 12. 날씨가 하는 일과 하지 않는 일

날씨는 TQQQ에 QQQ, SOXL에 SMH를 신호로 사용하고 SPY와 상대강도를 비교한다.

날씨는 현재 시장 상태를 설명하고 보고서에 기록하는 보조 정보다. 다음 항목에는 사용하지 않는다.

- 종목 선택 또는 추천
- 결제완료 USD 배분 결정
- 진행 중인 V4 주문의 가격·수량 변경
- `T` 또는 전략 규칙 변경

자금 배분은 사용자가 지정한 프로필, 금액, 적용 시점으로만 처리한다.

## 13. 상태를 읽는 법

| 상태 | 뜻 | 행동 |
|---|---|---|
| `OFF` | 신규 주문 차단 | 점검하거나 그대로 유지 |
| `ON` | 자동 실행 허용 | 모든 readiness 조건을 계속 확인 |
| `LOCKED` | 주문 또는 대사 결과가 불확실함 | 임의 해제 금지, 비상정지 후 대사 |

`RECONCILIATION_REQUIRED`가 있으면 DB증권과 로컬 상태가 맞지 않는다는 뜻이다. 새 주문은 차단되어야 한다.

## 14. 자주 읽을 파일

| 상대경로 | 쉬운 설명 |
|---|---|
| `README.md` | 설치부터 첫 점검까지 설명하는 사용자 안내서 |
| `docs/ruleset-1.md` | V4 계산식과 체결 규칙의 기준 문서 |
| `docs/operations.md` | 운영 명령 요약 |
| `docs/manuals/05-live-operations.md` | 실주문 ON/OFF와 장애 대응 |
| `docs/testbed-protocol.md` | 실주문을 열기 전에 필요한 최소수량 시험 |
| `docs/dbsec-capability-matrix.md` | 확인된 DB증권 기능과 아직 막혀 있는 기능 |
| `src/infinite_buying_dbapi/strategy.py` | 외부 의존성이 없는 V4 계산 코어 |
| `src/infinite_buying_dbapi/models.py` | 전략과 주문 데이터 계약 |
| `src/infinite_buying_dbapi/cli.py` | 실제 CLI 명령 구현 |
| `data/market/metadata.json` | 포함된 시장 데이터의 날짜 범위와 해시 |

## 15. 시작과 조회

저장소 루트에서 실행한다.

```powershell
uv sync --python 3.12
uv run app --help
```

다음은 주문을 보내지 않는 조회 명령이다.

```powershell
uv run app dbsec auth-status
uv run app dbsec balance
uv run app dbsec holdings
uv run app automation status --json
uv run app position status --json
uv run app orders list --json
uv run app capital status
```

잔고나 보유내역이 없는 새 계좌에서는 0건이 정상일 수 있다. DB증권의 `2679`는 이 경우 빈 결과로 처리한다. 다른 오류 코드는 빈 계좌라고 추측하지 않는다.

프로필 하나를 자세히 볼 때는 `PROFILE`을 실제 프로필 이름으로 바꾼다.

```powershell
uv run app position status PROFILE --json
uv run app position cycles PROFILE --json
uv run app position sessions PROFILE --cycle 1 --json
uv run app orders list --profile PROFILE --json
uv run app report daily --session-date latest --json
```

## 16. 전략과 날씨 확인

`preview`는 주문, outbox, 전략 상태를 기록하지 않는다.

```powershell
uv run app preview PROFILE --previous-close PRICE --completed-closes P1,P2,P3,P4,P5
```

날씨 조회는 로컬에 이미 저장된 값을 읽는다.

```powershell
uv run app weather current --symbol TQQQ --json
uv run app weather history --symbol TQQQ --limit 20 --json
```

다음 명령은 DB증권 일봉을 조회하고 로컬 시장 데이터와 날씨 스냅샷을 갱신한다. 읽기 전용 상태 조회와 다르므로 사용자가 갱신을 요청했을 때 실행한다.

```powershell
uv run app weather update --symbol TQQQ --json
```

SOXL은 `--symbol SOXL`을 사용한다.

## 17. 상태를 바꾸는 명령

아래 명령은 조회 전용이 아니다.

| 명령 | 실제 영향 |
|---|---|
| `automation on` | 프로필을 ON으로 바꿈 |
| `automation off` | 먼저 OFF로 바꾸고 미체결 취소·재조회를 시도함 |
| `automation tick` | ON 프로필에서 실제 주문 단계가 실행될 수 있음 |
| `reconcile` | DB증권과 비교해 로컬 대사 상태를 갱신함 |
| `capital apply` | 프로필 자금과 SQLite 상태를 변경함 |
| `emergency-stop on/off` | 전체 비상정지 상태를 변경함 |

Hermes는 사용자의 명시적 지시 없이 이 명령을 실행하지 않는다.

ON 전환 전에는 먼저 다음을 확인한다. 비상정지 해제도 상태 변경이므로 사용자가 명시적으로 지시해야 한다.

```powershell
uv run app emergency-stop off
uv run app automation readiness --profile PROFILE
uv run app automation on --help
```

사용자가 외부 실행환경 준비 완료와 정확한 프로필 ON을 명시했고 readiness의 모든 항목이 통과한 경우에만 현재 `--help` 계약대로 실행한다. capability를 문서 검토만으로 `확인됨` 처리하지 않는다.

`capital scan`은 DB증권 입출금·환전·결제내역 capability와 공식 응답 fixture가 확인될 때까지 실패하는 것이 정상이다. 결과를 추측하거나 SQLite에 자금 이벤트를 만들지 않는다.

## 18. 오류가 나면

timeout, 네트워크 오류, HTTP 5xx, 비정상 주문 응답은 주문 실패를 뜻하지 않는다. DB증권이 주문을 받았을 수도 있으므로 다음 순서를 따른다.

```powershell
uv run app emergency-stop on
uv run app orders list --json
uv run app backup create backups/before-reconcile.sqlite3
uv run app reconcile --profile PROFILE --json
```

- 같은 주문이나 취소를 반복하지 않는다.
- `UNKNOWN`, `LOCKED`, `RECONCILIATION_REQUIRED`를 임의로 지우지 않는다.
- SQLite를 직접 고치지 않는다.
- 진단 파일은 항상 `--redacted`로 만든다.

```powershell
uv run app diagnostics --output diagnostics/report.json --redacted
```

## 19. 출력 형식

`--json`을 지원하는 V2 운영·조회 명령은 보통 다음 공통 필드를 반환한다.

```text
schema_version, ok, data, warnings, errors, generated_at
```

`preview`는 envelope 없이 계산 결과 JSON을 반환한다. `dbsec balance`, `dbsec holdings` 같은 최소 노출 조회는 사람이 읽기 쉬운 텍스트를 반환한다.

- `ok=false` 또는 종료 코드가 0이 아니면 성공으로 해석하지 않는다.
- 자동 재시도하지 말고 오류 코드와 안전 조치를 보고한다.
- 주문, 체결, 현금, 날씨는 출력에 실제로 있는 값만 설명한다.
- 보이지 않는 계좌 상태나 주문 결과를 추측하지 않는다.

## 20. 이 저장소 밖에서 정할 것

다음 항목은 사용자가 별도 환경에서 정한다.

- Hermes skill 설치
- cron 또는 다른 실행 일정
- Slack과 메시지 전달
- Hermes Gateway
- 외부 서비스의 자격증명과 접근 권한

외부 구성이 끝난 뒤에도 프로젝트 조작에는 이 문서에 적힌 상대경로와 공개 CLI만 사용한다.
