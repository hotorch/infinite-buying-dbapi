# 백테스트 기본 시세 데이터

이 폴더에는 수강생이 인터넷이나 증권사 API 키 없이 백테스트를 실행할 수 있도록 TQQQ, SOXL, QQQ의 수정 일봉을 포함한다.

## 파일

| 파일 | 범위 | 거래일 수 |
|---|---|---:|
| `tqqq_adjusted_daily.csv` | 2010-02-11 ~ 2026-07-13 | 4,128 |
| `soxl_adjusted_daily.csv` | 2010-03-11 ~ 2026-07-13 | 4,109 |
| `qqq_adjusted_daily.csv` | 1999-03-10 ~ 2026-07-13 | 6,877 |
| `tqqq_regime_weather.csv` | 2010-12-28 ~ 2026-07-10 | 3,906 |

컬럼은 `date,symbol,open,high,low,close,volume` 순서다. 가격은 Toss Securities Open API의 일봉 요청에 `adjusted=true`를 지정해 받은 값을 그대로 저장했다. 자세한 요청 조건과 파일 해시는 `metadata.json`에 있다.

대시보드의 **최신 캔들 수집** 버튼은 저장된 마지막 날과 DB증권 수정 일봉이 같은지 먼저 확인한 뒤, TQQQ·SOXL과 비교지수 QQQ를 최근 완료된 미국 거래일까지 증분 갱신한다. 미국 장이 끝나지 않은 날의 캔들은 수집하지 않는다.

`tqqq_regime_weather.csv`는 EXP-009의 `live_2026h1` 결정 엔진과 Yahoo 수정주가 캐시로 만든 연구용 파생 데이터다. 각 `date` 행은 `signal_date` 종가까지 확인한 D-1 판정이며, 실시간 예보나 주문 지시가 아니다. 다음 명령으로 인수인계 프로젝트에서 다시 만들 수 있다.

```powershell
python scripts/export_regime_weather.py --source-repo 'C:\Users\hoyoung\Desktop\lazy-codex-toss-trading'
```

## 검증

레포 루트에서 다음 명령을 실행한다.

```powershell
uv run python scripts/validate_market_data.py
```

검증기는 다음을 확인한다.

- 파일 SHA-256
- 컬럼과 종목
- 행 수와 시작일·종료일
- 날짜 정렬과 중복
- 양수 가격과 OHLC 관계
- 검증 가능한 미국 거래소 달력 구간의 누락·비거래일

## 주의

이 데이터와 백테스트 결과는 미래 수익이나 성과를 보장하지 않는다. 공개 GitHub 레포에 배포하기 전에는 데이터 제공자의 재배포 조건을 별도로 확인해야 한다.
