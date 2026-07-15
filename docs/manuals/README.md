# 초보자용 전체 매뉴얼

처음 설치하는 분은 아래 순서대로 읽으세요.

1. [설치](01-installation.md)
2. [DB증권 Open API 신청과 인증](02-dbsec-api-setup.md)
3. [첫 프로필과 미리보기](03-first-preview.md)
4. [Hermes·Slack 자동화](04-hermes-automation.md)
5. [실주문 운영](05-live-operations.md)
6. [문제 해결](06-troubleshooting.md)
7. [보안·백업·수강생별 분리](07-security-and-backup.md)

참고 문서:

- [정확한 전략 규칙](../ruleset-1.md)
- [DB증권 기능 확인 현황](../dbsec-capability-matrix.md)
- [DB증권 양방향 LOC 시험 절차](../testbed-protocol.md)
- [개발자용 구현 계약](../implementation-plan.md)
- [운영 명령 요약](../operations.md)

문서와 실제 명령이 다르면 `uv run app --help`와 각 하위 명령의 `--help`를 우선 확인하고 관리자에게 보고하세요. 임의로 SQLite나 소스 코드를 수정하지 마세요.
