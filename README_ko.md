# Dryforge — 실험적 Mission / 세션 관리 Fork

사용자 의도를 유지하는 **Level 1** 아래에 기존 Dryforge를 **Level 2 Worker**로 둡니다.
Level 2는 **같은 세션**에서 한 번의 `ready → 승인 → go`를 완료하고 결과를 올립니다.
Level 1이 결과를 평가한 뒤 컨텍스트 여유가 확인되면 재사용하고, 아니면 체크포인트를
전달해 새 Worker를 생성합니다. Level 2가 임의로 다음 사이클을 정하지 않습니다.

`go`의 **Level 3**는 기존처럼 필요한 구현·조사·독립 검토를 수행합니다. 같은 작업의
수정은 세션을 재개할 수 있지만, 독립 리뷰에는 구현자의 세션을 재사용하지 않습니다.
새 에이전트는 명시적인 인계 자료를 읽으며, 이전 대화를 자동 상속한다고 가정하지 않습니다.

## 설치 및 사용

수정본은 `feature/mission-session-orchestration` 브랜치에 있습니다. 원본 플러그인 업데이트만으로
이 브랜치가 설치되지는 않습니다. Claude Code가 설치된 PC에서 로컬 플러그인으로 시험합니다.

```sh
git clone --branch feature/mission-session-orchestration --single-branch \
  https://github.com/contiloop/dryforge.git ~/dryforge-mission
# 실제 작업할 프로젝트 폴더에서 실행:
claude --plugin-dir ~/dryforge-mission/claude
```

`/mission` 또는 `/dryforge:mission`으로 시작하고, 먼저 목표·성공 기준·위임 권한·실행 한도를
확정합니다. Codex 배포본에도 `$mission`이 포함됩니다. 해당 클라이언트의 로컬 마켓플레이스
설치 방식으로 등록하고, 이름이 같은 두 플러그인이 동시에 활성화되지 않게 확인하세요.
기존 `/ready`, `/go`, `/migration`은 그대로 사용할 수 있습니다.

**권장 도구(선택 설치, Optional):** 공개 코드 검색용 **Grep MCP**, 문서 확인용 **Context7 MCP**.
둘 다 필수는 아니며 자동 설치하지 않습니다. [MCP 설정](docs/RESEARCH_MCP_SETUP.md)을 참고하세요.

## 구현 범위와 검증 한계

이번 확장은 스킬·세션 생명주기 규칙·테스트된 로컬 상태 관리 코드입니다.
**별도의 Claude/Codex SDK 상주 실행기나 전역 Hook 자동 설치 기능은 포함하지 않습니다.**
호스트가 실제 세션 생성/재개, 질문 중계, 하위 에이전트 생성 기능을 제공해야 합니다.
지원 여부가 확인되지 않으면 중단하며, 하나의 에이전트로 세 계층을 흉내 내지 않습니다.

승인은 문서 내용 해시에 연결하고, 준비와 구현 사이에 Level 2 세션이 바뀌면 거부합니다.
반복 실패·사이클 한도·오래된 승인·중복 이벤트·작업 중인 하위 에이전트도 검사합니다.
하지만 이 코드는 승인 기록의 일관성을 검증할 뿐, 실제 사람을 인증하거나 테스트 결과의
진위를 보증하지 않습니다. 권한·증거 검증은 신뢰할 수 있는 실행 환경의 책임입니다.

단위/정적 계약/패키지 검증과 실제 Claude/Codex 다중 에이전트 실행 검증은 다릅니다.
실제 환경에서 같은 ID의 ready/go, Level 3 호출, 질문 중계, 재사용/교체, 중단 복원을 확인해야 합니다.
자세한 사용법과 제한은 [Mission 가이드](docs/MISSION.md)를 참고하세요.

원본 소개와 설치 설명은 [보존된 한국어 README](README_ko.upstream.md)에 있습니다.
원본 Dryforge: prekuter. Apache-2.0. 원본 1.3.8 버전을 유지한 개발 브랜치이며 공식 릴리스가 아닙니다.
