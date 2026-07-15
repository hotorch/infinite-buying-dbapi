# 04. Hermes·Slack 자동화

V2에는 로컬 paper, Windows Task Scheduler, Slack SDK·웹훅이 없다. 계산 확인은 `app preview`, 일정과 Slack 전달은 Hermes Gateway가 담당한다.

1. Hermes 공식 Slack 설정에서 허용 사용자, 허용 채널, home channel을 지정한다.
2. `hermes-skills/operate-infinite-buying`을 Hermes에 설치한다.
3. skill 지침대로 `live-runner`, `capital-watch`, `morning-report`를 만들고 목록과 전달 대상을 확인한다.
4. `uv run app automation readiness --profile PROFILE`의 모든 check가 true인지 확인한다.
5. 그 후에만 Slack에서 실주문 시작을 지시한다.

cron과 Slack의 상세 설정은 [Hermes 핸드오프](../hermes-handoff.md)를 따른다. 토큰은 이 저장소에 저장하지 않는다.
