# 07. 보안·백업·수강생별 분리

APP KEY, APP SECRET, access token, 계좌번호는 `.env`, 로그, Slack, 진단 파일에 쓰지 않는다. 앱 자격증명은 Windows Credential Manager 또는 macOS Keychain, Slack 자격증명은 Hermes 저장소와 OS keychain에만 둔다.

```text
IB_DBSEC_ACCOUNT_MODE=real
IB_DBSEC_REQUESTS_PER_SECOND=<공식 증거로 확인한 값>
```

`IB_ENVIRONMENT`는 제거되었고 남아 있으면 마이그레이션 오류가 난다. 선택형 `IB_MAX_ORDER_NOTIONAL_USD`, `IB_MAX_DAILY_NOTIONAL_USD`는 운영자가 추가 상한을 원할 때만 설정한다.

수강생별로 OS 사용자, 계정 별칭, SQLite, OS keychain 항목, Hermes Slack allowlist를 분리한다. 데이터베이스는 직접 편집하지 않는다.

```powershell
uv run app backup create backups/state.sqlite3
uv run app diagnostics --output diagnostics/report.json --redacted
```

진단은 항상 redacted로 전달한다. 복원 전 모든 프로필을 OFF하고 미체결이 없는지 확인한다.
