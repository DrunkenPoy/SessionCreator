# /// script
# requires-python = ">=3.10"
# dependencies = ["mcp>=1.10,<2", "pywinpty>=2.0; sys_platform == 'win32'"]
# ///
"""
Session Hub — 프로젝트별 Claude Remote Control 세션 서버 관리 MCP (macOS / Windows)

설치할 때 고른 "루트 폴더" 아래의 하위 폴더 하나하나를 프로젝트로 보고,
프로젝트마다 `claude remote-control` 서버 모드를 상시 실행으로 띄워
Claude 앱(Code 탭)에서 프로젝트별로 새 세션을 만들 수 있게 한다.
  macOS   : launchd 에이전트 (재부팅 후 자동 실행)
  Windows : 시작프로그램 폴더의 숨김 런처 + 감독 프로세스(run-server), pywinpty로 pty 제공
            (로그인 시 자동 실행)

명령
  setup <루트폴더> [--name 관리세션이름]   설정 저장 + CLAUDE.md + MCP 등록
  install-manager                          관리 세션 서버를 상시 실행으로 등록
  uninstall-manager                        관리 세션 서버 등록 해제
  run-server <label>                       (Windows 내부용) 서버 감독 루프
  show-config                              현재 설정 출력
  serve (기본)                             MCP 서버로 실행

설정 파일: ~/.config/session-hub/config.json  (SESSION_HUB_CONFIG로 위치 변경)
환경 변수로 덮어쓰기(선택): SESSION_HUB_ROOT, SESSION_HUB_MANAGER_NAME,
  SESSION_HUB_CLAUDE_BIN, SESSION_HUB_AGENTS_DIR, SESSION_HUB_LOG_DIR,
  SESSION_HUB_LAUNCHCTL(테스트용), SESSION_HUB_STARTUP_DIR(Windows), SESSION_HUB_CLAUDE_JSON
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("SESSION_HUB_CONFIG", "~/.config/session-hub/config.json")).expanduser()
INSTALL_DIR = CONFIG_PATH.parent
LABEL_PREFIX = "com.sessionhub.rc"
IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
if IS_WIN:
    # 서버 등록 정보(spec json / pid 파일)를 두는 폴더, 로그 폴더, 로그인 시 자동 실행 폴더
    AGENTS_DIR = Path(os.environ.get("SESSION_HUB_AGENTS_DIR", str(INSTALL_DIR / "servers"))).expanduser()
    LOG_DIR = Path(os.environ.get(
        "SESSION_HUB_LOG_DIR",
        str(Path(os.environ.get("LOCALAPPDATA", "~/AppData/Local")).expanduser() / "session-hub" / "logs"))).expanduser()
    STARTUP_DIR = Path(os.environ.get(
        "SESSION_HUB_STARTUP_DIR",
        str(Path(os.environ.get("APPDATA", "~/AppData/Roaming")).expanduser()
            / "Microsoft/Windows/Start Menu/Programs/Startup"))).expanduser()
else:
    AGENTS_DIR = Path(os.environ.get("SESSION_HUB_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
    LOG_DIR = Path(os.environ.get("SESSION_HUB_LOG_DIR", "~/Library/Logs/session-hub")).expanduser()
    STARTUP_DIR = None
LAUNCHCTL = os.environ.get("SESSION_HUB_LAUNCHCTL", "launchctl")
CLAUDE_JSON = Path(os.environ.get("SESSION_HUB_CLAUDE_JSON", "~/.claude.json")).expanduser()
MCP_NAME = "session-hub"
MANAGER_KEY = "__manager__"
DEFAULT_MANAGER_NAME = "세션관리"
MD_BEGIN = "<!-- session-hub:begin -->"
MD_END = "<!-- session-hub:end -->"

RESTART_DELAY = 30  # 서버가 죽으면 이만큼 기다렸다가 재시작(초)
SPAWN_MODES = ("auto", "worktree", "same-dir")
PERMISSION_MODES = ("default", "acceptEdits", "plan", "bypassPermissions")
_BAD_NAME = re.compile(r"[/\\:\x00-\x1f\x7f]")

MANAGER_CLAUDE_MD = f"""{MD_BEGIN}
# 세션 관리 AI

이 폴더는 프로젝트들을 모아두는 루트다. 이 폴더에서 열린 세션은 **세션 관리 전용**이다.
개별 프로젝트의 실제 작업(코드 수정 등)은 여기서 하지 않고, 해당 프로젝트 세션에서 한다.

## 할 일
- 새 프로젝트 요청 → `{MCP_NAME}` MCP의 `create_project`로 폴더와 세션 서버를 함께 만든다.
  - 이름은 사용자가 말한 그대로 쓴다. 애매하면 한 번만 확인한다.
  - 코드 프로젝트(UE5, Unity 등)는 `git_init=true`(기본값). 문서/마케팅처럼 git이 필요 없으면 `git_init=false`.
  - 사용자가 설명을 주면 `description`에 넣는다. 그 프로젝트 CLAUDE.md의 첫 내용이 된다.
- 이미 있는 폴더에 세션만 필요 → `start_session_server`.
- 서버를 띄운 뒤 `server_status`로 로그를 확인하고, 정상이면 이렇게 알린다:
  "Claude 앱 Code 탭에서 **<프로젝트 이름>** 을 골라 새 세션을 만드세요."
- 오류가 보이면 로그 핵심 줄을 보여주고 원인을 설명한다. 로그에 신뢰(trust) 오류가 있을 때만 `trust_project` 후 재시작.

## 하지 않을 일
- 프로젝트 폴더나 파일을 삭제하지 않는다. 원하면 사용자가 직접 지우도록 안내한다.
- 하위 프로젝트 안의 코드를 수정하지 않는다.
- `permission_mode="bypassPermissions"`는 사용자가 명시적으로 요청했을 때만 쓴다.
{MD_END}
"""


# ───────────────────────── 설정 ─────────────────────────

def _load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if os.environ.get("SESSION_HUB_ROOT"):
        cfg["root"] = os.environ["SESSION_HUB_ROOT"]
    if os.environ.get("SESSION_HUB_MANAGER_NAME"):
        cfg["manager_name"] = os.environ["SESSION_HUB_MANAGER_NAME"]
    cfg.setdefault("manager_name", DEFAULT_MANAGER_NAME)
    return cfg


def _root() -> Path:
    root = _load_config().get("root")
    if not root:
        raise RuntimeError("루트 폴더가 설정되지 않았습니다. 먼저 `setup <루트폴더>`를 실행하세요.")
    return Path(root).expanduser().resolve()


def _manager_name() -> str:
    return _load_config()["manager_name"]


# ───────────────────────── 공통 유틸 ─────────────────────────

def _check_platform() -> None:
    if not (IS_MAC or IS_WIN):
        raise RuntimeError(f"지원하지 않는 OS입니다 ({sys.platform}). macOS와 Windows만 지원합니다.")


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _label(key: str, root: Path | None = None) -> str:
    root = root or _root()
    h = hashlib.sha1(f"{root}\0{key}".encode("utf-8")).hexdigest()[:12]
    return f"{LABEL_PREFIX}.{h}"


def _plist_path(key: str) -> Path:
    """등록 정보 파일: macOS는 launchd plist, Windows는 spec json."""
    return AGENTS_DIR / f"{_label(key)}{'.json' if IS_WIN else '.plist'}"


def _pid_path(key: str) -> Path:
    return AGENTS_DIR / f"{_label(key)}.pid"


def _launcher_path(key: str) -> Path:
    return STARTUP_DIR / f"session-hub-{_label(key)}.vbs"


def _log_path(key: str) -> Path:
    return LOG_DIR / f"{_label(key)}.log"


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("프로젝트 이름이 비어 있습니다.")
    if len(name) > 100:
        raise ValueError("프로젝트 이름은 100자 이하여야 합니다.")
    if name.startswith(".") or _BAD_NAME.search(name):
        raise ValueError("프로젝트 이름에 '/', '\\', ':', 제어 문자를 쓸 수 없고 '.'으로 시작할 수 없습니다.")
    return name


def _project_dir(name: str) -> Path:
    name = _validate_name(name)
    root = _root()
    path = (root / name).resolve()
    if path.parent != root:
        raise ValueError("프로젝트는 루트 폴더 바로 아래에만 만들 수 있습니다.")
    return path


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)


def _find_bin(name: str, env_key: str | None = None) -> str | None:
    if env_key and os.environ.get(env_key):
        return os.environ[env_key]
    found = shutil.which(name)
    if found:
        return found
    if IS_WIN:
        appdata = Path(os.environ.get("APPDATA", "~/AppData/Roaming")).expanduser()
        cands = [Path(f"~/.local/bin/{name}.exe").expanduser(),
                 Path(f"~/.claude/local/{name}.exe").expanduser(),
                 Path(f"~/.claude/local/{name}.cmd").expanduser(),
                 appdata / "npm" / f"{name}.cmd",
                 appdata / "npm" / f"{name}.exe"]
    else:
        cands = [Path(c).expanduser() for c in (
            f"~/.local/bin/{name}", f"~/.claude/local/{name}",
            f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}")]
    for p in cands:
        if p.exists():
            return str(p)
    return None


def _find_claude() -> str:
    found = _find_bin("claude", "SESSION_HUB_CLAUDE_BIN")
    if not found:
        raise FileNotFoundError("claude 실행 파일을 찾지 못했습니다. SESSION_HUB_CLAUDE_BIN 환경 변수로 경로를 지정하세요.")
    return found


def _launch_path_env(claude_bin: str) -> str:
    dirs = [str(Path(claude_bin).parent), "/opt/homebrew/bin", "/usr/local/bin",
            str(Path("~/.local/bin").expanduser()), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]
    dirs += os.environ.get("PATH", "").split(":")
    seen, out = set(), []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return ":".join(out)


def _has_commit(path: Path) -> bool:
    if not (path / ".git").exists():
        return False
    return _run(["git", "rev-parse", "--verify", "HEAD"], cwd=path).returncode == 0


def _resolve_spawn(path: Path, spawn: str) -> str:
    if spawn not in SPAWN_MODES:
        raise ValueError(f"spawn은 {SPAWN_MODES} 중 하나여야 합니다.")
    if spawn == "auto":
        return "worktree" if _has_commit(path) else "same-dir"
    if spawn == "worktree" and not _has_commit(path):
        raise ValueError("worktree 모드는 커밋이 하나 이상 있는 git 레포에서만 쓸 수 있습니다.")
    return spawn


def _service_state_mac(key: str) -> dict:
    res = _run([LAUNCHCTL, "print", f"{_domain()}/{_label(key)}"])
    if res.returncode != 0:
        return {"loaded": False, "running": False}
    text = res.stdout
    state = re.search(r"^\s*state = (\S+)", text, re.M)
    pid = re.search(r"^\s*pid = (\d+)", text, re.M)
    last_exit = re.search(r"^\s*last exit code = (.+)$", text, re.M)
    return {
        "loaded": True,
        "running": bool(state and state.group(1) == "running"),
        "pid": int(pid.group(1)) if pid else None,
        "last_exit": last_exit.group(1).strip() if last_exit else None,
    }


def _tail(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])


def _bootout_mac(key: str) -> None:
    _run([LAUNCHCTL, "bootout", f"{_domain()}/{_label(key)}"])
    for _ in range(10):
        if not _service_state_mac(key)["loaded"]:
            return
        time.sleep(0.3)


# ── Windows 백엔드: 시작프로그램 숨김 런처 + 감독 프로세스(run-server) ──

def _pid_alive(pid: int) -> bool:
    res = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"])
    return res.returncode == 0 and f'"{pid}"' in res.stdout


def _read_pid(key: str) -> int | None:
    try:
        return int(_pid_path(key).read_text().strip())
    except (OSError, ValueError):
        return None


def _service_state_win(key: str) -> dict:
    if not _plist_path(key).exists():
        return {"loaded": False, "running": False}
    pid = _read_pid(key)
    alive = bool(pid and _pid_alive(pid))
    return {"loaded": True, "running": alive, "pid": pid if alive else None, "last_exit": None}


def _bootout_win(key: str) -> None:
    pid = _read_pid(key)
    if pid and _pid_alive(pid):
        _run(["taskkill", "/T", "/F", "/PID", str(pid)])  # 감독 프로세스와 자식(claude) 모두 종료
    _pid_path(key).unlink(missing_ok=True)


def _service_state(key: str) -> dict:
    _check_platform()
    return _service_state_win(key) if IS_WIN else _service_state_mac(key)


def _bootout(key: str) -> None:
    _check_platform()
    _bootout_win(key) if IS_WIN else _bootout_mac(key)


def _unregister(key: str) -> bool:
    """재부팅/로그인 후 다시 뜨지 않도록 등록 파일을 지운다. 지운 게 있으면 True."""
    removed = False
    targets = [_plist_path(key)]
    if IS_WIN:
        targets += [_launcher_path(key), _pid_path(key)]
    for p in targets:
        if p.exists():
            p.unlink()
            removed = removed or p == _plist_path(key)
    return removed


def _register(key: str, display_name: str, workdir: Path, spawn: str,
              permission_mode: str | None) -> dict:
    _check_platform()
    if permission_mode and permission_mode not in PERMISSION_MODES:
        raise ValueError(f"permission_mode는 {PERMISSION_MODES} 중 하나여야 합니다.")
    return (_register_win if IS_WIN else _register_mac)(key, display_name, workdir, spawn, permission_mode)


def _vbs_quote(s: str) -> str:
    return s.replace('"', '""')


def _register_win(key: str, display_name: str, workdir: Path, spawn: str,
                  permission_mode: str | None) -> dict:
    claude_bin = _find_claude()
    uv = _find_bin("uv")
    if not uv:
        raise FileNotFoundError("uv 실행 파일을 찾지 못했습니다. https://docs.astral.sh/uv/ 에서 설치하세요.")
    script = INSTALL_DIR / "session_hub_mcp.py"
    if not script.exists():
        script = Path(__file__).resolve()
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)

    argv = [claude_bin, "remote-control", "--spawn", spawn, "--name", display_name]
    if permission_mode:
        argv += ["--permission-mode", permission_mode]
    log = str(_log_path(key))
    spec = {"label": _label(key), "key": key, "argv": argv, "cwd": str(workdir), "log": log,
            "env": {"SESSION_HUB_ROOT": str(_root()), "SESSION_HUB_PROJECT": key}}

    _bootout(key)
    _plist_path(key).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    cmd = subprocess.list2cmdline([uv, "run", "--script", str(script), "run-server", _label(key)])
    launcher = _launcher_path(key)
    launcher.write_text(f'CreateObject("WScript.Shell").Run "{_vbs_quote(cmd)}", 0, False\r\n', encoding="utf-8")
    # 로그인 때까지 기다리지 않고 지금 바로 숨김 실행
    subprocess.Popen(["wscript.exe", "//B", "//Nologo", str(launcher)],
                     creationflags=0x00000008 | 0x00000200 | 0x08000000)  # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    for _ in range(20):  # 감독 프로세스가 pid 파일을 쓸 때까지 대기
        if _read_pid(key):
            break
        time.sleep(0.5)
    time.sleep(2)
    return {
        "name": display_name, "path": str(workdir), "spawn": spawn,
        "label": _label(key), "spec": str(_plist_path(key)), "launcher": str(launcher), "log": log,
        **_service_state(key),
        "recent_log": _tail(Path(log), 15),
    }


def _run_server_loop(label: str) -> None:
    """(Windows) 서버를 pty 위에서 실행하고 죽으면 재시작하는 감독 루프. 시작프로그램 런처가 호출한다."""
    from winpty import PtyProcess
    spec_path = AGENTS_DIR / f"{label}.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    pid_file = AGENTS_DIR / f"{label}.pid"
    pid_file.write_text(str(os.getpid()))
    log = Path(spec["log"])
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **spec["env"]}
    argv = list(spec["argv"])
    if argv[0].lower().endswith((".cmd", ".bat")):
        argv = ["cmd.exe", "/c"] + argv
    while spec_path.exists():
        if log.exists() and log.stat().st_size > 1_000_000:
            log.replace(log.with_suffix(".log.old"))
        with open(log, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} 시작: {' '.join(argv)}\n")
            f.flush()
            proc = PtyProcess.spawn(argv, cwd=spec["cwd"], env=env)  # 입력을 닫지 않으므로 EOF로 종료되지 않는다
            try:
                while True:
                    f.write(proc.read(4096))
                    f.flush()
            except EOFError:
                pass
            f.write(f"\n--- 종료 (exit {proc.exitstatus}), {RESTART_DELAY}초 후 재시작\n")
        time.sleep(RESTART_DELAY)
    pid_file.unlink(missing_ok=True)


def _register_mac(key: str, display_name: str, workdir: Path, spawn: str,
                  permission_mode: str | None) -> dict:
    claude_bin = _find_claude()
    AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # remote-control은 터미널이 없으면 연결되지 않으므로 script로 pty를 붙여 실행한다.
    # 입력이 끊기면(EOF) 종료되므로 tail -f /dev/null 로 stdin을 열어 둔다.
    cmd = ["/usr/bin/script", "-q", "/dev/null", claude_bin, "remote-control",
           "--spawn", spawn, "--name", display_name]
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    args = ["/bin/sh", "-c", "tail -f /dev/null | exec " + " ".join(shlex.quote(a) for a in cmd)]

    log = str(_log_path(key))
    plist = {
        "Label": _label(key),
        "ProgramArguments": args,
        "WorkingDirectory": str(workdir),
        "EnvironmentVariables": {
            "PATH": _launch_path_env(claude_bin),
            "HOME": str(Path.home()),
            "LANG": "ko_KR.UTF-8",
            "SESSION_HUB_ROOT": str(_root()),
            "SESSION_HUB_PROJECT": key,
        },
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": RESTART_DELAY,
        "ProcessType": "Interactive",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    path = _plist_path(key)
    _bootout(key)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    res = _run([LAUNCHCTL, "bootstrap", _domain(), str(path)])
    if res.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap 실패: {res.stderr.strip() or res.stdout.strip()}")
    time.sleep(2)
    return {
        "name": display_name, "path": str(workdir), "spawn": spawn,
        "label": _label(key), "plist": str(path), "log": log,
        **_service_state(key),
        "recent_log": _tail(Path(log), 15),
    }


def _registered_keys(root: Path | None = None) -> dict[str, Path]:
    """이 루트에 속한 등록 서버만 돌려준다."""
    root = root or _root()
    out = {}
    if not AGENTS_DIR.exists():
        return out
    for p in AGENTS_DIR.glob(f"{LABEL_PREFIX}.*.json" if IS_WIN else f"{LABEL_PREFIX}.*.plist"):
        try:
            if IS_WIN:
                env = json.loads(p.read_text(encoding="utf-8")).get("env", {})
            else:
                with open(p, "rb") as f:
                    env = plistlib.load(f).get("EnvironmentVariables", {})
            if env.get("SESSION_HUB_ROOT") == str(root) and env.get("SESSION_HUB_PROJECT"):
                out[env["SESSION_HUB_PROJECT"]] = p
        except Exception:
            continue
    return out


# ───────────────────────── MCP 도구 ─────────────────────────

def list_projects() -> dict:
    """루트 폴더의 프로젝트 목록과 각 프로젝트 세션 서버 상태를 보여준다."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    registered = _registered_keys(root)
    projects = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
        reg = d.name in registered
        projects.append({
            "name": d.name,
            "git": (d / ".git").exists(),
            "server_registered": reg,
            **(_service_state(d.name) if reg else {"loaded": False, "running": False}),
        })
    return {
        "root": str(root),
        "manager_name": _manager_name(),
        "manager": _service_state(MANAGER_KEY) if MANAGER_KEY in registered else None,
        "projects": projects,
        "orphan_servers": sorted(k for k in registered if k != MANAGER_KEY and not (root / k).is_dir()),
    }


def create_project(name: str, description: str = "", git_init: bool = True,
                   start_server: bool = True, spawn: str = "auto",
                   permission_mode: str | None = None) -> dict:
    """루트 아래에 새 프로젝트 폴더를 만들고, 원하면 그 폴더 전용 세션 서버까지 띄운다."""
    path = _project_dir(name)
    if path.exists():
        raise FileExistsError(f"이미 있는 폴더입니다: {path}. 서버만 띄우려면 start_session_server를 쓰세요.")
    path.mkdir(parents=True)
    body = description.strip()
    (path / "CLAUDE.md").write_text(f"# {path.name}\n\n{body}\n" if body else f"# {path.name}\n", encoding="utf-8")

    git_info = None
    if git_init:
        (path / ".gitignore").write_text(".DS_Store\nThumbs.db\n.claude/worktrees/\n", encoding="utf-8")
        commit = ["git", "commit", "-q", "-m", "Initial commit (session hub)"]
        if not _run(["git", "config", "user.email"], cwd=path).stdout.strip():
            commit = ["git", "-c", "user.name=Session Hub", "-c", "user.email=session-hub@localhost"] + commit[1:]
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"], commit):
            r = _run(cmd, cwd=path)
            if r.returncode != 0:
                git_info = f"git 단계 실패 ({' '.join(cmd[:2])}): {r.stderr.strip()}"
                break
        else:
            git_info = "git init + 첫 커밋 완료"

    result = {"name": path.name, "path": str(path), "git": git_info, "trust": None, "server": None}
    if start_server:
        # launchd 서버는 터미널이 없어 신뢰 확인창에 답할 수 없으므로 미리 신뢰 처리한다.
        result["trust"] = _trust_path(path)
        result["server"] = start_session_server(path.name, spawn=spawn, permission_mode=permission_mode)
    return result


def start_session_server(name: str, spawn: str = "auto", permission_mode: str | None = None) -> dict:
    """기존 프로젝트 폴더에 세션 서버를 등록(또는 재시작)한다. 재부팅 후에도 자동 실행된다."""
    path = _project_dir(name)
    if not path.is_dir():
        raise FileNotFoundError(f"프로젝트 폴더가 없습니다: {path}")
    return _register(path.name, path.name, path, _resolve_spawn(path, spawn), permission_mode)


def stop_session_server(name: str, unregister: bool = True) -> dict:
    """프로젝트 세션 서버를 멈춘다. unregister=True면 재부팅 후에도 다시 뜨지 않게 등록을 지운다.
    프로젝트 폴더와 파일은 건드리지 않는다."""
    key = _validate_name(name)
    _bootout(key)
    removed = _unregister(key) if unregister else False
    return {"name": key, "stopped": not _service_state(key)["loaded"], "unregistered": removed}


def server_status(name: str, log_lines: int = 40) -> dict:
    """프로젝트 세션 서버의 상태와 최근 로그를 보여준다. 관리 세션 자신은 name='__manager__'."""
    key = MANAGER_KEY if name == MANAGER_KEY else _validate_name(name)
    return {
        "name": key, "registered": _plist_path(key).exists(),
        **_service_state(key),
        "log": str(_log_path(key)),
        "recent_log": _tail(_log_path(key), max(1, min(log_lines, 400))),
    }


def _trust_path(path: Path) -> dict:
    if not CLAUDE_JSON.exists():
        raise FileNotFoundError(f"{CLAUDE_JSON} 파일이 없습니다. claude를 한 번 실행해 로그인하세요.")
    backup = CLAUDE_JSON.with_name(CLAUDE_JSON.name + f".bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(CLAUDE_JSON, backup)
    data = json.loads(CLAUDE_JSON.read_text(encoding="utf-8"))
    projects = data.setdefault("projects", {})
    # Windows에서는 Claude가 경로를 슬래시(C:/...)로 저장할 수 있어 두 표기 모두 신뢰 처리한다.
    keys = {str(path)} | ({path.as_posix()} if IS_WIN else set())
    already = True
    for k in keys:
        entry = projects.setdefault(k, {})
        already = already and bool(entry.get("hasTrustDialogAccepted"))
        entry["hasTrustDialogAccepted"] = True
    tmp = CLAUDE_JSON.with_name(CLAUDE_JSON.name + ".tmp-session-hub")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CLAUDE_JSON)
    return {"path": str(path), "already_trusted": already, "backup": str(backup)}


def trust_project(name: str) -> dict:
    """[선택] 폴더 신뢰 확인을 미리 '수락'으로 표시한다. ~/.claude.json을 백업한 뒤 수정한다.
    server_status 로그에 신뢰(trust) 관련 오류가 보일 때만 사용."""
    path = _project_dir(name)
    if not path.is_dir():
        raise FileNotFoundError(f"프로젝트 폴더가 없습니다: {path}")
    return {**_trust_path(path), "next": "start_session_server로 서버를 재시작하세요."}


# ───────────────────────── CLI ─────────────────────────

def _write_claude_md(root: Path) -> str:
    md = root / "CLAUDE.md"
    if not md.exists():
        md.write_text(MANAGER_CLAUDE_MD, encoding="utf-8")
        return "생성"
    text = md.read_text(encoding="utf-8")
    if MD_BEGIN in text and MD_END in text:
        start, end = text.index(MD_BEGIN), text.index(MD_END) + len(MD_END)
        md.write_text(text[:start] + MANAGER_CLAUDE_MD.strip() + text[end:], encoding="utf-8")
        return "갱신"
    md.write_text(text.rstrip() + "\n\n" + MANAGER_CLAUDE_MD, encoding="utf-8")
    return "기존 내용 뒤에 추가"


def cmd_setup(root_arg: str, manager_name: str, register_mcp: bool, force: bool) -> None:
    _check_platform()
    root = Path(root_arg).expanduser().resolve()

    old = _load_config().get("root") if CONFIG_PATH.exists() else None
    if old and Path(old).expanduser().resolve() != root and not force:
        old_regs = _registered_keys(Path(old).expanduser().resolve())
        if old_regs:
            sys.exit(f"이전 루트({old})에 등록된 서버가 {len(old_regs)}개 있습니다.\n"
                     f"먼저 정리하거나(uninstall-manager, stop_session_server) --force로 진행하세요.")

    root.mkdir(parents=True, exist_ok=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    # 스크립트를 고정 위치에 복사 (다운로드 폴더를 지워도 동작하도록)
    me = Path(__file__).resolve()
    installed = INSTALL_DIR / "session_hub_mcp.py"
    if not installed.exists() or installed.resolve() != me:
        shutil.copy2(me, installed)

    CONFIG_PATH.write_text(json.dumps({"root": str(root), "manager_name": manager_name},
                                      ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✔ 설정 저장: {CONFIG_PATH}")
    print(f"  루트 폴더: {root}")
    print(f"  관리 세션 이름: {manager_name}")
    print(f"✔ MCP 스크립트 설치: {installed}")
    print(f"✔ {root / 'CLAUDE.md'}: {_write_claude_md(root)}")

    mcp_cmd = ["claude", "mcp", "add", "--scope", "local", MCP_NAME, "--",
               "uv", "run", "--script", str(installed)]
    registered = False
    if register_mcp:
        claude = _find_bin("claude", "SESSION_HUB_CLAUDE_BIN")
        uv = _find_bin("uv")
        if claude and uv:
            mcp_cmd[0], mcp_cmd[7] = claude, uv
            _run([claude, "mcp", "remove", "--scope", "local", MCP_NAME], cwd=root)
            r = _run(mcp_cmd, cwd=root)
            registered = r.returncode == 0
            if not registered:
                print(f"✘ MCP 자동 등록 실패: {(r.stderr or r.stdout).strip()}")
        else:
            print(f"✘ {'claude' if not claude else 'uv'}를 찾지 못해 MCP를 자동 등록하지 못했습니다.")
    if registered:
        print(f"✔ MCP 등록 완료 ('{MCP_NAME}', 이 루트 폴더에서 연 세션에서만 보임)")
    else:
        print("\n아래 명령으로 직접 등록하세요:")
        print(f"  cd {_q(root)} && {' '.join(_q(a) for a in mcp_cmd)}")

    print(f"""
다음 단계
  1) 루트 폴더 신뢰 수락:  cd {_q(root)} && claude    → 신뢰 확인 Yes → /mcp 로 연결 확인 → /exit
  2) Remote Control 첫 실행 확인:  claude remote-control --spawn same-dir --name 테스트   → Connected 확인 후 Ctrl+C
  3) 관리 세션 상시 등록:  uv run --script {_q(installed)} install-manager
""")


def _q(s) -> str:
    s = str(s)
    return subprocess.list2cmdline([s]) if IS_WIN else shlex.quote(s)


def cmd_install_manager() -> None:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    print(json.dumps(_register(MANAGER_KEY, _manager_name(), root, "same-dir", None), ensure_ascii=False, indent=2))


def cmd_uninstall_manager() -> None:
    _bootout(MANAGER_KEY)
    _unregister(MANAGER_KEY)
    print("관리 세션 서버 등록을 해제했습니다.")


def cmd_serve() -> None:
    from mcp.server.fastmcp import FastMCP
    try:
        root_desc = f"루트 폴더 {_root()}"
    except RuntimeError:
        root_desc = "루트 폴더(아직 미설정 — 사용자에게 setup 실행을 안내할 것)"
    mcp = FastMCP(
        MCP_NAME,
        instructions=(
            f"{root_desc} 아래의 프로젝트 폴더와, 프로젝트별 Claude Remote Control 세션 서버를 관리한다. "
            "새 프로젝트는 create_project, 기존 폴더에 서버만 띄울 땐 start_session_server를 쓴다. "
            "서버를 띄운 뒤에는 server_status로 로그를 확인해 정상 연결됐는지 보고한다. "
            "stop_session_server는 폴더를 지우지 않는다. 폴더 삭제는 이 서버의 기능이 아니다."
        ),
    )
    for fn in (list_projects, create_project, start_session_server,
               stop_session_server, server_status, trust_project):
        mcp.tool()(fn)
    mcp.run()


def main() -> None:
    ap = argparse.ArgumentParser(prog="session_hub_mcp.py")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("setup", help="루트 폴더 설정 + CLAUDE.md + MCP 등록")
    s.add_argument("root", help="프로젝트들을 모아둘 루트 폴더 (예: ~/Projects)")
    s.add_argument("--name", default=DEFAULT_MANAGER_NAME, help="관리 세션 이름 (기본: 세션관리)")
    s.add_argument("--no-mcp", action="store_true", help="MCP 자동 등록 생략")
    s.add_argument("--force", action="store_true", help="이전 루트에 서버가 남아 있어도 진행")
    sub.add_parser("install-manager")
    r = sub.add_parser("run-server", help="(Windows 내부용) 서버 감독 루프")
    r.add_argument("label")
    sub.add_parser("uninstall-manager")
    sub.add_parser("show-config")
    sub.add_parser("serve")
    a = ap.parse_args()

    if a.cmd == "setup":
        cmd_setup(a.root, a.name, not a.no_mcp, a.force)
    elif a.cmd == "run-server":
        _run_server_loop(a.label)
    elif a.cmd == "install-manager":
        cmd_install_manager()
    elif a.cmd == "uninstall-manager":
        cmd_uninstall_manager()
    elif a.cmd == "show-config":
        print(json.dumps({"config_file": str(CONFIG_PATH), **_load_config()}, ensure_ascii=False, indent=2))
    else:
        cmd_serve()


if __name__ == "__main__":
    main()
