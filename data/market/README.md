# 백테스트 시장 데이터

`app weather update --symbol TQQQ|SOXL --json`이 DB증권 수정 일봉을 원자적으로 갱신한다. 대상은 TQQQ, SOXL, QQQ, SMH, SPY다. QQQ는 TQQQ 신호, SMH는 SOXL 신호, SPY는 공통 비교지수다.

신규 설치에 SMH/SPY 파일이 없으면 최근 800일을 bootstrap한 뒤 `regime-weather-1`을 계산한다. 저장 파일은 `date,symbol,open,high,low,close,volume` 순서이며 중복·누락 거래일, 비정상 OHLC, 기존 overlap 수정주가 불일치가 있으면 전체 쓰기를 거부한다.

`tqqq_regime_weather.csv`는 배포된 V1 백테스트 결과의 읽기 전용 호환 자료다. V2 갱신 후에는 내장 엔진이 생성한 QQQ/SMH/SPY 기반 결과가 우선하며 외부 저장소나 export script를 호출하지 않는다.

검증:

```powershell
uv run python scripts/validate_market_data.py
```

시장 데이터의 재배포 조건은 공급자 약관을 별도로 확인한다. 과거 데이터와 백테스트는 미래 성과를 보장하지 않는다.
