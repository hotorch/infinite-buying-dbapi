# 01. Windows 설치

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

`setup`, `preview`, `profile`, `run`, `orders`, `live`, `backup` 등이 보이면 성공입니다.

## 업데이트할 때

관리자가 전달한 새 버전으로 파일을 교체하기 전에 반드시 백업하세요.

```powershell
uv run app emergency-stop on
uv run app backup create backups/before-update.sqlite3
uv sync --python 3.12
```

전략 버전이 달라졌다면 자동으로 기존 프로필을 변경하지 말고 변경 안내와 마이그레이션 문서를 확인하세요.

## 제거할 때

프로젝트 폴더만 먼저 삭제하지 마세요. 백업과 Windows 자격 증명 관리자에 저장된 키 처리 방법을 관리자에게 확인하세요.
