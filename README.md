# SessionCreator

[한국어](README.ko.md) | **English**

An MCP server (macOS) that manages one **Claude Remote Control** session server per project.

Pick a root folder once. Every sub-folder becomes a project, and each project gets its own `claude remote-control` server running as a launchd agent. You then create new sessions per project from the **Code tab** of the Claude app, and a "manager" session at the root can create new projects for you.

## Requirements

- macOS (uses launchd)
- [Claude Code](https://claude.com/claude-code) (`claude`), logged in with a subscription account
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)

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

`setup`, `install-manager`, `uninstall-manager`, `show-config`, `serve` (default, runs the MCP server).

## How it works

- Each server runs `claude remote-control --spawn <auto|worktree|same-dir> --name <project>` as a launchd agent (`RunAtLoad`, `KeepAlive`), so it comes back after a reboot. `auto` uses `worktree` when the project is a git repo with at least one commit, otherwise `same-dir`.
- `claude remote-control` does not connect without a terminal, so the agent runs it under `script` (a pty) with stdin kept open.
- `create_project` marks the new folder as trusted (it edits `~/.claude.json` after making a timestamped backup), because a launchd agent cannot answer the trust prompt. Note that this skips Claude's folder trust dialog for folders created through this tool.
- Logs: `~/Library/Logs/session-hub/`. LaunchAgents: `~/Library/LaunchAgents/com.sessionhub.rc.*.plist`.

## Environment variables (optional)

`SESSION_HUB_CONFIG`, `SESSION_HUB_ROOT`, `SESSION_HUB_MANAGER_NAME`, `SESSION_HUB_CLAUDE_BIN`, `SESSION_HUB_AGENTS_DIR`, `SESSION_HUB_LOG_DIR`, `SESSION_HUB_LAUNCHCTL`, `SESSION_HUB_CLAUDE_JSON`

## Uninstall

```bash
uv run --script ~/.config/session-hub/session_hub_mcp.py uninstall-manager
# for each project: ask the manager session to run stop_session_server, or
launchctl bootout gui/$(id -u)/<label> && rm ~/Library/LaunchAgents/<label>.plist
claude mcp remove --scope local session-hub   # run inside the root folder
```

## License

[MIT](LICENSE)
