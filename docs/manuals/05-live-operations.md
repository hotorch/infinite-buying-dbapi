# 05. 실주문 운영

> 이 문서는 기술 절차입니다. 법률·배포·위험고지 검토를 대신하지 않습니다.

## 실주문 전 체크리스트

- [ ] TQQQ/SOXL 20 또는 40분할 프로필
- [ ] 모의계좌 양방향 LOC 프로토콜 성공
- [ ] 사용 TR별 호출 제한 확인
- [ ] 20거래일 Shadow 운영 통과
- [ ] 법률·저작권·위험고지 검토 완료
- [ ] 주문별·일별 최대금액 설정 확인
- [ ] 백업 생성

검증 결과 기록:

```powershell
uv run app capability verify --opposing-loc-confirmed --rate-limits-confirmed --evidence "검증보고서 경로와 날짜"
```

설치 단위 live 활성화:

```powershell
uv run app live enable --legal-review-ack --risk-disclosure-ack
```

비상정지 해제와 당일 승인:

```powershell
uv run app emergency-stop off
uv run app live approve-today --session-date 2026-07-13
```

## 매도 단계

```powershell
uv run app run sell-phase p1 --session-date 2026-07-13 --environment live
```

프로그램이 토큰, 체결·미체결, 잔고, 완료된 일봉을 조회합니다. 대조 실패 시 주문은 제출되지 않습니다.

## 매수 단계

DB증권 앱에서 매도 주문 접수를 확인한 뒤:

```powershell
uv run app run buy-phase p1 --session-date 2026-07-13 --environment live
```

매수 직전 다시 대조하고 주문가능금액·수량을 확인합니다.

## 자동 스케줄 등록

충분한 수동 운용 후에만 등록하세요.

```powershell
uv run app scheduler install p1 --confirm
```

Windows 작업은 5분마다 상태를 확인하지만 실제 단계는 미국 프리마켓/정규장 기준 15분 실행창 안에서 한 번만 실행합니다. 실패한 작업은 다음 tick에서 대조 후 재개하고, 완료된 작업은 반복하지 않습니다.

## 운영 종료

```powershell
uv run app orders list
uv run app backup create backups/end-of-day.sqlite3
uv run app diagnostics --output diagnostics/end-of-day.json --redacted
```
