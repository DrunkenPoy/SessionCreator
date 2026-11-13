# SessionCreator

**한국어** | [English](README.md)

프로젝트마다 **Claude Remote Control** 세션 서버를 하나씩 관리하는 MCP 서버입니다 (macOS).

루트 폴더를 한 번 정하면 그 아래의 하위 폴더가 각각 프로젝트가 되고, 프로젝트마다 `claude remote-control` 서버가 launchd 에이전트로 실행됩니다. Claude 앱의 **Code 탭**에서 프로젝트별로 새 세션을 만들 수 있고, 루트의 "관리 세션"이 새 프로젝트도 만들어 줍니다.

## 요구 사항

- macOS (launchd 사용)
- [Claude Code](https://claude.com/claude-code) (`claude`), 구독 계정으로 로그인
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

## 설치

```bash
git clone https://github.com/DrunkenPoy/SessionCreator.git
cd SessionCreator
uv run --script session_hub_mcp.py setup ~/Projects   # 루트 폴더
```

`setup`이 하는 일:

1. 설정을 `~/.config/session-hub/config.json`에 저장
2. 스크립트를 `~/.config/session-hub/session_hub_mcp.py`로 복사
3. 루트에 `CLAUDE.md`를 만들거나 갱신 (이 폴더에서 연 세션이 관리 세션이 됨)
4. 루트 폴더에 `session-hub` MCP 등록 (`--scope local`)

이후 한 번만 하면 됩니다.

1. `cd ~/Projects && claude` → 폴더 신뢰 확인 Yes → `/mcp`로 연결 확인 → `/exit`
2. 관리 세션 상시 등록:
   ```bash
   uv run --script ~/.config/session-hub/session_hub_mcp.py install-manager
   ```

옵션: `--name <관리 세션 이름>` (기본 `세션관리`), `--no-mcp`, `--force`.

## MCP 도구

| 도구 | 설명 |
| --- | --- |
| `list_projects` | 루트 아래 프로젝트와 각 서버 상태 목록 |
| `create_project` | 폴더 생성 (+ `CLAUDE.md`, 선택적 `git init`) 후 세션 서버 시작 |
| `start_session_server` | 기존 폴더에 서버 등록 또는 재시작 |
| `stop_session_server` | 서버 중지 (선택적으로 등록 해제). 파일은 지우지 않음 |
| `server_status` | 상태와 최근 로그 |
| `trust_project` | `~/.claude.json`에서 폴더를 신뢰로 표시 (먼저 백업) |

## CLI 명령

`setup`, `install-manager`, `uninstall-manager`, `show-config`, `serve` (기본값, MCP 서버 실행).

## 동작 방식

- 각 서버는 `claude remote-control --spawn <auto|worktree|same-dir> --name <프로젝트>`를 launchd 에이전트(`RunAtLoad`, `KeepAlive`)로 실행하므로 재부팅 후에도 다시 뜹니다. `auto`는 커밋이 하나 이상 있는 git 레포면 `worktree`, 아니면 `same-dir`입니다.
- `claude remote-control`은 터미널이 없으면 연결되지 않아서, 에이전트가 `script`(pty) 아래에서 stdin을 열어 둔 채 실행합니다.
- `create_project`는 launchd 에이전트가 신뢰 확인창에 답할 수 없어서 새 폴더를 자동으로 신뢰 처리합니다 (타임스탬프 백업 후 `~/.claude.json` 수정). 이 도구로 만든 폴더는 Claude의 폴더 신뢰 확인을 건너뛴다는 점에 유의하세요.
- 로그: `~/Library/Logs/session-hub/`, LaunchAgent: `~/Library/LaunchAgents/com.sessionhub.rc.*.plist`

## 환경 변수 (선택)

`SESSION_HUB_CONFIG`, `SESSION_HUB_ROOT`, `SESSION_HUB_MANAGER_NAME`, `SESSION_HUB_CLAUDE_BIN`, `SESSION_HUB_AGENTS_DIR`, `SESSION_HUB_LOG_DIR`, `SESSION_HUB_LAUNCHCTL`, `SESSION_HUB_CLAUDE_JSON`

## 제거

```bash
uv run --script ~/.config/session-hub/session_hub_mcp.py uninstall-manager
# 프로젝트마다: 관리 세션에 stop_session_server를 요청하거나
launchctl bootout gui/$(id -u)/<label> && rm ~/Library/LaunchAgents/<label>.plist
claude mcp remove --scope local session-hub   # 루트 폴더 안에서 실행
```

## 라이선스

[MIT](LICENSE)
