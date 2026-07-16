# 07. 보안·백업·수강생별 분리

APP KEY, APP SECRET, access token, 계좌번호는 `.env`, 로그, 메시지, 진단 파일에 쓰지 않습니다. 앱 자격증명은 Windows Credential Manager 또는 macOS Keychain에만 둡니다. 외부 Hermes 연결의 자격증명은 사용자가 별도 환경에서 관리합니다.

```text
IB_DBSEC_ACCOUNT_MODE=real
IB_DBSEC_REQUESTS_PER_SECOND=<공식 증거로 확인한 값>
```

`IB_ENVIRONMENT`는 제거되었습니다. 남아 있으면 마이그레이션 오류가 납니다. 선택형 `IB_MAX_ORDER_NOTIONAL_USD`, `IB_MAX_DAILY_NOTIONAL_USD`는 운영자가 추가 상한을 원할 때만 설정합니다.

수강생별로 OS 사용자, 계정 별칭, SQLite, OS keychain 항목을 분리합니다. 외부 Hermes 사용자와 채널도 별도로 나눕니다. 데이터베이스는 직접 편집하지 않습니다.

```powershell
uv run app backup create backups/state.sqlite3
uv run app diagnostics --output diagnostics/report.json --redacted
```

진단 파일은 항상 redacted 상태로 전달합니다. 복원 전에는 모든 프로필을 OFF로 만들고 미체결이 없는지 확인합니다. OFF 과정에서 취소 결과가 불명확하면 복원하지 말고 `LOCKED` 상태에서 대사합니다.
