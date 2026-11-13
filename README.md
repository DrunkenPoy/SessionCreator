# SessionCreator

[한국어](README.ko.md) | **English**

An MCP server (macOS / Windows) that manages one **Claude Remote Control** session server per project.

Pick a root folder once. Every sub-folder becomes a project, and each project gets its own always-on `claude remote-control` server (a launchd agent on macOS, a hidden login-startup process on Windows). You then create new sessions per project from the **Code tab** of the Claude app, and a "manager" session at the root can create new projects for you.

## How is this different from the official `claude remote-control`?

This project is **not a replacement** for Claude's official Remote Control. It is a thin manager on top of it: the actual remote access, session creation and app connection are all done by the official `claude remote-control` command. SessionCreator only takes care of the chores around it.

| | Official `claude remote-control` alone | With SessionCreator |
| --- | --- | --- |
| Starting a server | Run it by hand in a terminal and keep that terminal open | Starts automatically (launchd on macOS, login startup on Windows) and restarts if it dies |
| After a reboot / terminal closed | Connection is gone until you run it again | Comes back by itself (on macOS at boot, on Windows at login) |
| Many projects | One manual command per folder | One root folder; every sub-folder is a project with its own server |
| New project | Create the folder, `git init`, `CLAUDE.md`, start the server yourself | Tell the manager session "create project X": it does all of it |
| No terminal available | Needs a terminal (pty) | Provides one for you (`script` on macOS, `pywinpty` on Windows) |
| Folder trust prompt | Answer it interactively | Pre-accepted for folders created by this tool (`~/.claude.json` is backed up first) |

It is also different from **Claude Code on the web** (cloud sessions): those run in Anthropic's cloud containers, while sessions here run on **your own computer, in your real project folders**, with your local files and tools (Unreal, Unity, etc.).

Things to keep in mind:

- It is an unofficial wrapper. If `claude remote-control` changes its options or behavior, this project may need an update.
- Pre-accepting the trust prompt skips a safety confirmation, but only for folders created through this tool.
- If the official tool adds auto-start or multi-project management itself, parts of this project will become unnecessary.

## Requirements

- macOS (launchd) or Windows 10/11 (login-startup launcher)
- [Claude Code](https://claude.com/claude-code) (`claude`), logged in with a subscription account
- [uv](https://docs.astral.sh/uv/) (`brew install uv` / `winget install astral-sh.uv`)

## Setup

```bash
git clone https://github.com/DrunkenPoy/SessionCreator.git
cd SessionCreator
uv run --script session_hub_mcp.py setup ~/Projects   # your root folder
```

`setup` will:

1. Save the config to `~/.config/session-hub/config.json`
2. Copy the script to `~/.config/session-hub/session_hub_mcp.py`
3. Create (or update) `CLAUDE.md` in the root, which turns sessions opened there into manager sessions
4. Register the `session-hub` MCP server for the root folder (`--scope local`)

Then, once:

1. `cd ~/Projects && claude` → accept the folder trust prompt → check `/mcp` → `/exit`
2. Register the always-on manager session:
   ```bash
   uv run --script ~/.config/session-hub/session_hub_mcp.py install-manager
   ```

Options: `--name <manager session name>` (default `세션관리`), `--no-mcp`, `--force`.

## MCP tools

| Tool | What it does |
| --- | --- |
| `list_projects` | Lists projects under the root and the state of each server |
| `create_project` | Creates a folder (+ `CLAUDE.md`, optional `git init`) and starts its session server |
| `start_session_server` | Registers or restarts a server for an existing folder |
| `stop_session_server` | Stops a server (and optionally unregisters it). Never deletes files |
| `server_status` | Shows state and recent log lines |
| `trust_project` | Marks a folder as trusted in `~/.claude.json` (backed up first) |

## CLI commands

`setup`, `install-manager`, `uninstall-manager`, `show-config`, `serve` (default, runs the MCP server), `run-server <label>` (Windows internal).

## How it works

- Each server runs `claude remote-control --spawn <auto|worktree|same-dir> --name <project>` as a launchd agent (`RunAtLoad`, `KeepAlive`), so it comes back after a reboot. `auto` uses `worktree` when the project is a git repo with at least one commit, otherwise `same-dir`.
- `claude remote-control` does not connect without a terminal, so the agent runs it under `script` (a pty) with stdin kept open.
- `create_project` marks the new folder as trusted (it edits `~/.claude.json` after making a timestamped backup), because a launchd agent cannot answer the trust prompt. Note that this skips Claude's folder trust dialog for folders created through this tool.
- Logs: `~/Library/Logs/session-hub/`. LaunchAgents: `~/Library/LaunchAgents/com.sessionhub.rc.*.plist`.
- **Windows**: each server is a hidden `.vbs` launcher in your Startup folder (starts at login, no admin rights needed) that runs `session_hub_mcp.py run-server <label>`. That supervisor runs `claude remote-control` inside a pty (via `pywinpty`, installed automatically by `uv`) and restarts it after 30 s if it exits. Specs/pid files: `~/.config/session-hub/servers/`, logs: `%LOCALAPPDATA%\session-hub\logs\`. Servers start at login, not at boot.

## Environment variables (optional)

`SESSION_HUB_CONFIG`, `SESSION_HUB_ROOT`, `SESSION_HUB_MANAGER_NAME`, `SESSION_HUB_CLAUDE_BIN`, `SESSION_HUB_AGENTS_DIR`, `SESSION_HUB_LOG_DIR`, `SESSION_HUB_LAUNCHCTL`, `SESSION_HUB_STARTUP_DIR` (Windows), `SESSION_HUB_CLAUDE_JSON`

## Uninstall

```bash
uv run --script ~/.config/session-hub/session_hub_mcp.py uninstall-manager
# for each project: ask the manager session to run stop_session_server, or
launchctl bootout gui/$(id -u)/<label> && rm ~/Library/LaunchAgents/<label>.plist
claude mcp remove --scope local session-hub   # run inside the root folder
```

On Windows, `stop_session_server` / `uninstall-manager` stop the process and delete the Startup launcher.

## License

[MIT](LICENSE)
