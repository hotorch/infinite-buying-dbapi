# 01. Windows 설치

이 문서는 Windows용 순서입니다. macOS 사용자는 README의 macOS 안내에 따라 `uv`를 설치한 뒤 `uv sync --python 3.12`부터 같은 명령을 사용할 수 있습니다.

## 준비물

- Windows 11
- 인터넷 연결
- PowerShell
- 프로젝트 폴더

## 1단계: PowerShell 열기

시작 메뉴에서 `PowerShell`을 검색해 실행합니다. 일반 설치에는 관리자 권한이 필요하지 않습니다.

## 2단계: 프로젝트 폴더로 이동

```powershell
cd C:\Users\hoyoung\Desktop\infinite-buying-dbapi
```

다른 위치에 설치했다면 자신의 경로로 바꾸세요. 현재 위치 확인:

```powershell
Get-Location
Get-ChildItem
```

`pyproject.toml`, `README.md`, `src`, `docs`가 보여야 합니다.

## 3단계: uv 설치

```powershell
winget install --id=astral-sh.uv -e
```

PowerShell을 닫았다가 다시 연 후 확인합니다.

```powershell
uv --version
```

## 4단계: Python 환경 설치

```powershell
uv sync --python 3.12
```

이 명령은 프로젝트 폴더의 `.venv`에 전용 Python을 준비합니다. 다른 프로젝트의 Python과 섞이지 않습니다.

## 5단계: 프로그램 확인

```powershell
uv run app --help
```

`setup`, `preview`, `profile`, `run`, `orders`, `automation`, `weather`, `position`, `backup` 등이 보이면 성공입니다. `live`와 `scheduler`는 0.2.0 명령이 아닙니다.

## 업데이트할 때

관리자가 전달한 새 버전으로 파일을 교체하기 전에 반드시 백업하세요.

```powershell
uv run app emergency-stop on
uv run app backup create backups/before-update.sqlite3
uv sync --python 3.12
```

전략 버전이 달라졌다면 기존 프로필을 자동으로 바꾸지 말고 변경 안내와 마이그레이션 문서를 먼저 확인하세요. 현재 앱은 `0.2.0`, 전략은 `pure-v4-ruleset-1`입니다.

## 제거할 때

프로젝트 폴더만 먼저 삭제하지 마세요. 백업과 Windows 자격 증명 관리자에 저장된 키 처리 방법을 관리자에게 확인하세요.
