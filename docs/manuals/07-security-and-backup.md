# 07. 보안·백업·수강생별 분리

## 비밀정보 저장 위치

APP_KEY, APP_SECRET, Access Token과 만료시각은 Windows 자격 증명 관리자에 저장합니다. `.env`에는 비밀이 아닌 실행 설정만 둡니다. 발급 JSON을 옮기기 위해 `DB_APPKEY`, `DB_APPSECRET`을 임시로 넣었다면 `--import-env-credentials` 성공 직후 두 줄을 삭제합니다.

`.env`에 둘 수 있는 예:

```text
IB_ACCOUNT_ALIAS=student-001
IB_ENVIRONMENT=preview
IB_DBSEC_OAUTH_STYLE=form
IB_DBSEC_REQUESTS_PER_SECOND=공식확인값
IB_MAX_ORDER_NOTIONAL_USD=1000
IB_MAX_DAILY_NOTIONAL_USD=2000
```

`DB_ENV=real`은 DB증권 자격증명 환경이고 `IB_ENVIRONMENT=preview|paper|live`는 프로그램 실행 모드입니다. 이름이 비슷해도 서로 대체할 수 없습니다.

## 수강생별 분리

- 가능하면 수강생마다 별도 Windows 사용자 계정을 사용합니다.
- 계좌 별칭에 실제 계좌번호를 쓰지 않습니다.
- 데이터베이스와 백업 폴더를 공유하지 않습니다.
- 모의계좌 키와 실계좌 키를 같은 별칭에 섞지 않습니다.
- 진단보고서를 전달하기 전에 파일명에도 계좌번호가 없는지 확인합니다.

## 백업

```powershell
uv run app backup create backups/state-20260713.sqlite3
```

주요 시점마다 백업합니다.

- 첫 프로필 생성 후
- live 활성화 전
- 프로그램 업데이트 전
- 전략 버전 변경 전
- 대조 오류를 해결한 후

## 복원

먼저 비상정지를 켜고 현재 DB도 별도로 백업합니다.

```powershell
uv run app emergency-stop on
uv run app backup create backups/before-restore.sqlite3
uv run app backup restore backups/restore-target.sqlite3 --confirm
```

복원 명령은 SQLite 무결성 검사를 통과한 파일만 적용합니다. 복원 후 DB증권 잔고·주문과 다시 대조하기 전에는 신규 주문을 보내지 않습니다.

## 지원 요청 전 점검

```powershell
uv run app diagnostics --output diagnostics/support.json --redacted
```

보고서를 메모장으로 열어 키, 토큰, 계좌번호가 없는지 한 번 더 확인한 뒤 전달하세요.
