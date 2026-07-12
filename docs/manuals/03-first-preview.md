# 03. 첫 프로필과 미리보기

## 프로필이란?

프로필은 `어느 계좌 별칭에서 어떤 종목을 몇 분할, 얼마의 자본으로 운용할지` 저장한 설정입니다.

처음에는 TQQQ 40분할을 권장합니다.

```powershell
uv run app profile create p1 --symbol TQQQ --division 40 --capital 10000
```

- `p1`: 사용자가 정한 프로필 이름
- `TQQQ`: 종목
- `40`: 분할수
- `10000`: 미화 10,000달러

프로필 확인:

```powershell
uv run app profile list
```

## 미리보기 실행

```powershell
uv run app preview p1 --previous-close 100 --completed-closes 96,97,98,99,100
```

예시 값은 연습용입니다. 실제 운용에서는 DB증권 일봉 조회값을 사용합니다.

## 결과를 읽는 법

결과는 JSON 한 줄로 출력됩니다.

- `sell`: 매도 주문 의도 목록
- `buy`: 매수 주문 의도 목록
- `quantity`: 정수 주문수량
- `limit_price`: LOC·지정가 기준
- `planned_t_effect`: 완전체결 시 T 변화량
- `reason_code`: 주문 생성 이유
- `input_hash`: 입력 상태가 같았음을 확인하는 해시
- `intent_id`: 같은 거래일 같은 역할의 중복주문을 막는 ID

보유수량이 0이면 매도 목록은 비어 있고 최초 LOC 매수만 보이는 것이 정상입니다.

## 30분할 안내

30분할은 일반화된 공식을 사용하는 실험 프로필입니다. preview, paper, replay는 가능하지만 live는 코드에서 거부합니다.

## 계산 결과가 비어 있을 때

- 1주도 살 수 없는 예산일 수 있습니다.
- 대조가 필요한 상태일 수 있습니다.
- 리버스 첫날이라 매수하지 않는 날일 수 있습니다.
- 해당 단계에 생성할 주문이 없을 수 있습니다.

`0주 주문`을 억지로 만들지 않는 것이 정상적인 안전 동작입니다.
