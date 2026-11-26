# SessionCreator

**한국어** | [English](README.md)

프로젝트마다 **Claude Remote Control** 세션 서버를 하나씩 관리하는 MCP 서버입니다 (macOS / Windows).

루트 폴더를 한 번 정하면 그 아래의 하위 폴더가 각각 프로젝트가 되고, 프로젝트마다 `claude remote-control` 서버가 상시 실행됩니다 (macOS는 launchd 에이전트, Windows는 로그인 시 시작되는 숨김 프로세스). Claude 앱의 **Code 탭**에서 프로젝트별로 새 세션을 만들 수 있고, 루트의 "관리 세션"이 새 프로젝트도 만들어 줍니다.

## 공식 `claude remote-control`과 뭐가 다른가요?

이 프로젝트는 Claude 공식 Remote Control을 **대체하지 않습니다**. 그 위에 얹은 얇은 관리 도구입니다. 실제 원격 접속, 세션 생성, 앱 연결은 전부 공식 `claude remote-control` 명령이 하고, SessionCreator는 그 주변의 번거로운 일만 대신 처리합니다.

| | 공식 `claude remote-control`만 쓸 때 | SessionCreator를 쓸 때 |
| --- | --- | --- |
| 서버 실행 | 터미널에서 직접 실행하고 창을 계속 열어 둠 | 자동 실행 (macOS는 launchd, Windows는 로그인 시 시작), 죽으면 재시작 |
| 재부팅 / 터미널 종료 후 | 다시 실행할 때까지 연결 끊김 | 알아서 다시 뜸 (macOS는 부팅 시, Windows는 로그인 시) |
| 프로젝트가 여러 개 | 폴더마다 명령을 따로 실행 | 루트 폴더 하나에 하위 폴더가 각각 프로젝트, 서버도 각각 |
| 새 프로젝트 | 폴더, `git init`, `CLAUDE.md`, 서버 실행을 직접 | 관리 세션에 "X 프로젝트 만들어줘"라고 하면 전부 처리 |
| 터미널이 없는 환경 | 터미널(pty)이 필요 | 대신 붙여 줌 (macOS는 `script`, Windows는 `pywinpty`) |
| 폴더 신뢰 확인창 | 직접 대화형으로 응답 | 이 도구로 만든 폴더는 미리 수락 (`~/.claude.json`을 먼저 백업) |

**Claude Code on the web**(클라우드 세션)과도 다릅니다. 그쪽은 Anthropic 클라우드 컨테이너에서 실행되지만, 여기서 만드는 세션은 **내 컴퓨터의 실제 프로젝트 폴더**에서 실행되므로 로컬 파일과 로컬 도구(Unreal, Unity 등)를 그대로 쓸 수 있습니다.

알아둘 점:

- 비공식 래퍼입니다. `claude remote-control`의 옵션이나 동작이 바뀌면 이 프로젝트도 수정해야 할 수 있습니다.
- 신뢰 확인창을 미리 수락하는 건 안전 확인을 건너뛰는 것이지만, 이 도구로 만든 폴더에만 적용됩니다.
- 공식 도구가 나중에 자동 실행이나 여러 프로젝트 관리를 직접 지원하면 이 프로젝트의 일부는 필요 없어질 수 있습니다.

## 요구 사항

- macOS (launchd) 또는 Windows 10/11 (로그인 시작 런처 방식)
- [Claude Code](https://claude.com/claude-code) (`claude`), 구독 계정으로 로그인
- [uv](https://docs.astral.sh/uv/) (`brew install uv` / `winget install astral-sh.uv`)

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

`setup`, `install-manager`, `uninstall-manager`, `show-config`, `serve` (기본값, MCP 서버 실행), `run-server <label>` (Windows 내부용).

## SessionCreator 스킬

[SKILL.md](SKILL.md)에 에이전트의 도구 호출 기준, Windows·macOS 설치 절차, 로컬 MCP 설정 템플릿과 요청 예제를 담았습니다. 스킬을 사용하려면 사용자 PC에서 SessionCreator의 로컬 `session-hub` MCP 서버를 연결해야 합니다.

## 동작 방식

- 각 서버는 `claude remote-control --spawn <auto|worktree|same-dir> --name <프로젝트>`를 launchd 에이전트(`RunAtLoad`, `KeepAlive`)로 실행하므로 재부팅 후에도 다시 뜹니다. `auto`는 커밋이 하나 이상 있는 git 레포면 `worktree`, 아니면 `same-dir`입니다.
- `claude remote-control`은 터미널이 없으면 연결되지 않아서, 에이전트가 `script`(pty) 아래에서 stdin을 열어 둔 채 실행합니다.
- `create_project`는 launchd 에이전트가 신뢰 확인창에 답할 수 없어서 새 폴더를 자동으로 신뢰 처리합니다 (타임스탬프 백업 후 `~/.claude.json` 수정). 이 도구로 만든 폴더는 Claude의 폴더 신뢰 확인을 건너뛴다는 점에 유의하세요.
- 로그: `~/Library/Logs/session-hub/`, LaunchAgent: `~/Library/LaunchAgents/com.sessionhub.rc.*.plist`
- **Windows**: 서버마다 시작프로그램 폴더에 숨김 `.vbs` 런처가 만들어지고(관리자 권한 불필요, 로그인 시 실행), 이것이 `session_hub_mcp.py run-server <label>` 감독 프로세스를 띄웁니다. 감독 프로세스는 `pywinpty`(uv가 자동 설치)로 pty 안에서 `claude remote-control`을 실행하고, 종료되면 30초 후 재시작합니다. 등록 정보: `~/.config/session-hub/servers/`, 로그: `%LOCALAPPDATA%\session-hub\logs\`. 부팅이 아니라 로그인 시점에 시작됩니다.

## 환경 변수 (선택)

`SESSION_HUB_CONFIG`, `SESSION_HUB_ROOT`, `SESSION_HUB_MANAGER_NAME`, `SESSION_HUB_CLAUDE_BIN`, `SESSION_HUB_AGENTS_DIR`, `SESSION_HUB_LOG_DIR`, `SESSION_HUB_LAUNCHCTL`, `SESSION_HUB_STARTUP_DIR`(Windows), `SESSION_HUB_CLAUDE_JSON`

## 제거

```bash
uv run --script ~/.config/session-hub/session_hub_mcp.py uninstall-manager
# 프로젝트마다: 관리 세션에 stop_session_server를 요청하거나
launchctl bootout gui/$(id -u)/<label> && rm ~/Library/LaunchAgents/<label>.plist
claude mcp remove --scope local session-hub   # 루트 폴더 안에서 실행
```

Windows에서는 `stop_session_server` / `uninstall-manager`가 프로세스를 종료하고 시작프로그램 런처를 지웁니다.

## 라이선스

[MIT](LICENSE)
