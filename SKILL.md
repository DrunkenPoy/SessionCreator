---
name: session-creator
description: Manage project-specific Claude Remote Control servers through the local SessionCreator MCP on Windows or macOS. Use when the user asks to list projects, create a project, start or stop its remote session server, or diagnose a connection from the Claude app's Code tab.
---

# SessionCreator

SessionCreator manages one Claude Remote Control server per immediate subfolder of a user-selected projects root. Call the local `session-hub` MCP tools for project and server management. To open a coding session, select the project in the Claude app's **Code** tab.

SessionCreator runs on the user's Windows 10/11 or macOS machine and connects to the agent over local stdio. Claude Code handles the Remote Control connection and account sign-in. The agent needs access to the locally registered MCP server to call its tools.

## Set up the local server

If `session-hub` is already available, call `list_projects` to verify the configured root and continue. If it is missing, give the user the setup steps for their OS. Run setup only when the user asks for installation and has selected the projects root.

Install [Claude Code](https://claude.com/claude-code) and sign in with an account that can use Remote Control. Install [uv](https://docs.astral.sh/uv/) and have Git available to clone the repository and initialize Git projects.

**Windows (PowerShell)**

```powershell
git clone https://github.com/DrunkenPoy/SessionCreator.git
Set-Location SessionCreator
$projectRoot = Join-Path $env:USERPROFILE 'Projects'
uv run --script .\session_hub_mcp.py setup "$projectRoot"
Set-Location -LiteralPath $projectRoot
claude
```

**macOS**

```bash
git clone https://github.com/DrunkenPoy/SessionCreator.git
cd SessionCreator
uv run --script ./session_hub_mcp.py setup "$HOME/Projects"
cd "$HOME/Projects"
claude
```

Replace the example projects root with the user's chosen directory. For an existing clone, start in its directory and skip the clone step. Setup saves the root, installs the script under `~/.config/session-hub/`, updates the root's `CLAUDE.md`, and registers `session-hub` for that root in Claude Code.

From Claude Code in the projects root, review the folder trust prompt, run `/mcp` to check for `session-hub`, then exit Claude Code. From that same directory, run `claude remote-control --spawn same-dir --name SessionCreator-Test` and stop the test with Ctrl+C after it connects. To make the root manager available from the Claude app, run `install-manager` using the installed script:

| Platform | Command |
| --- | --- |
| Windows PowerShell | `uv run --script "$env:USERPROFILE/.config/session-hub/session_hub_mcp.py" install-manager` |
| macOS | `uv run --script "$HOME/.config/session-hub/session_hub_mcp.py" install-manager` |

Run Claude Code from the projects root to use the local registration. If the agent runs in a cloud-only environment without access to this stdio server, direct the user to their local Claude Code session.

### Manual MCP configuration

If automatic registration fails, run `claude mcp add --scope local session-hub -- uv run --script "<absolute-installed-script-path>" serve` from the projects root. Replace the placeholder with the installed script path printed by setup.

For a local MCP client that accepts a `mcpServers` JSON object, use this template. Replace both placeholders with absolute paths on the user's machine. In JSON, escape Windows backslashes or use forward slashes.

```json
{
  "mcpServers": {
    "session-hub": {
      "command": "<absolute-path-to-uv>",
      "args": ["run", "--script", "<absolute-installed-script-path>", "serve"]
    }
  }
}
```

## Choose the MCP tool

| User request | Action |
| --- | --- |
| List projects or find a project name | Call `list_projects` and use the exact name returned. |
| Create a project | Call `create_project` with `name` and any user-provided `description`. Git initialization and server startup default to true. Set `start_server=false` for a folder-only request. |
| Start or restart a server for an existing project | Call `start_session_server` with its exact name. Leave `spawn` at `auto` unless the user requests a specific mode. |
| Check why a server is unavailable | Call `server_status` with its name. Use `__manager__` for the root manager. Report the relevant log lines. |
| Stop a project server | Call `stop_session_server`. Set `unregister=false` for a temporary stop. The default `unregister=true` also removes its automatic startup registration. Project files are preserved. |

After creating a project with startup enabled or starting a server, call `server_status`. Check both the process state and recent logs before reporting a successful Remote Control connection. On Windows, a running supervisor alone only confirms that the supervisor is alive. If connection evidence is missing, report the observed state and have the user check the Claude app's **Code** tab.

Creating a project with startup enabled backs up and updates `~/.claude.json` to trust the new folder. For an existing folder with a trust error, ask the user to review its trust prompt in local Claude Code. Use `trust_project` only when there is a trust error and the user explicitly asks you to mark that folder as trusted. Keep Claude Code's default permission mode.

## Examples

- **“Create a Git project called Shader Lab for Unreal material experiments and make it available remotely.”** Call `create_project` with `{"name":"Shader Lab","description":"Unreal material experiments","git_init":true}`. Check `server_status` for `Shader Lab`, then tell the user where to open it in the Code tab if connected.
- **“Turn on Remote Control for my existing UE Prototype folder.”** Use `list_projects` to resolve the name, then call `start_session_server` and `server_status` for that project.
- **“Stop Shader Lab for now, but start it again at my next login.”** Call `stop_session_server` with `{"name":"Shader Lab","unregister":false}` and report whether the stop succeeded.

Source and issue tracker are available in the [MIT-licensed SessionCreator repository](https://github.com/DrunkenPoy/SessionCreator).
