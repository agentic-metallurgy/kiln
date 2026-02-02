# Kiln

Kiln orchestrates Claude Code instances on your local machine using GitHub projects as its control panel.

When you move issues from one column to another, Kiln invokes Claude to run the corresponding /command.

Claude creates the worktrees, researches the codebase, creates and implements the plan.

It's designed to be simple, requires very little setup:

- **Use your existing Claude subscription** (no auth trickery, no API keys needed, runs locally)
- **All context and state is on GitHub** (no markdown mess, no local DBs, easy recovery)
- **Poll instead of webhooks/events** (no external attack surfaces, works behind VPN)
- **Supports MCPs and anything else Claude can do**

That's the heart of it and it works because… it's Claude :)

![End-to-end demo](docs/end-to-end-flow.gif)

## Installation and How-To

See the [User Guide](docs/user-guide.md) for setup instructions.

## What it looks like

| ⚪ Backlog | 🔵 Research | 🟣 Plan | 🟠 Implement | 🟡 Validate | 🟢 Done |
|-----------|-------------|---------|--------------|-------------|---------|
| *new issues* | *codebase exploration* | *design tasks* | *write code* | *human review* | *complete* |

| Column    | What Claude Does                                        | Labels                                  |
|-----------|---------------------------------------------------------|-----------------------------------------|
| Backlog   | —                                                       | —                                       |
| Research  | Explores codebase, writes findings to issue             | researching → research_ready            |
| Plan      | Designs implementation, writes plan to issue            | planning → plan_ready                   |
| Implement | Executes plan, commits code, opens PR, iterates on review | implementing → reviewing → (Validate) |
| Validate  | Nothing; Human review — merge PR when ready             | —                                       |
| Done      | Worktree cleaned up automatically                       | cleaned_up                              |

## Design Principles

### 🔥 Claude CLI as Execution Engine

Execute workflows via the `claude` CLI rather than direct API calls.

- **Zero auth setup**: Leverages existing `claude` and `gh` logins—no API keys or OAuth flows to configure
- **Commit attribution**: Git commits are attributed to the authenticated user without external auth dependencies
- **Full capabilities**: Claude CLI supports slash commands, tools, file access, and git operations
- **Streaming**: Native support for long-running operations with streaming output

### 🔥 Polling Over Webhooks

Use periodic polling instead of webhook-based event handling.

- **Security-first**: No external attack surface from exposed endpoints
- **Firewall-friendly**: Works behind VPNs without requiring publicly-accessible endpoints
- **No infrastructure**: Eliminates need for public URLs, SSL certificates, or webhook secret management
- **Simplicity**: Single process, no web server, no ngrok tunnels, no cloud functions

**Trade-off**: 30-second latency (configurable) vs. near-instant webhook response.

### 🔥 GitHub Labels as State Machine

Use GitHub labels as the primary workflow state machine rather than database state.

- **Crash recovery**: Daemon restarts automatically resume from label state
- **Visibility**: Engineers can see workflow state directly on issues
- **Manual override**: Labels can be manually added/removed to force state transitions
- **Distributed-safe**: Multiple daemon instances won't conflict

### 🔥 Issues as Product Requirements Docs

Research and plan outputs are written and iterated on in the issue description to keep a single source of truth with auditable progression.

## Config

1. Run `./run.sh` — first run scaffolds a fresh config file
2. Edit `.kiln/config`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GITHUB_TOKEN` | Yes | - | GitHub PAT (classic) with required scopes |
| `PROJECT_URLS` | Yes | - | Comma-separated GitHub Project URLs |
| `ALLOWED_USERNAME` | Yes | - | GitHub username authorized to trigger workflows |
| `POLL_INTERVAL` | No | 30 | Seconds between polls |
| `WATCHED_STATUSES` | No | Research,Plan,Implement | Status columns to monitor |
| `MAX_CONCURRENT_WORKFLOWS` | No | 3 | Parallel workflow limit |
| `STAGE_MODELS` | No | see below | Claude model per workflow stage |

### 🔥 Special Labels

These labels trigger autonomous workflows:

| Label | Effect |
|-------|--------|
| ![yolo](docs/label-yolo.svg) | Autonomously push through until PR is made |
| ![reset](docs/label-reset.svg) | Clears all research, plan, labels, worktrees, and sends to Backlog |

### 🔥 Stage Models Default

| Stage | Model | Rationale |
|-------|-------|-----------|
| Prepare | haiku | Fast, simple worktree setup |
| Research | opus | Deep codebase exploration |
| Plan | opus | Complex architectural reasoning |
| Implement: Code | opus | Code generation from plan |
| Implement: Review | sonnet | PR review iteration |
| Comment Iteration | sonnet | Feedback processing in Research/Plan |

### 🔥 GHES Log Masking

For GitHub Enterprise Server users, Kiln automatically masks sensitive hostname and organization information in log files to prevent accidental exposure.

| Config | Default | Description |
|--------|---------|-------------|
| `GHES_LOGS_MASK` | `true` | Enable/disable log masking |

When enabled (default), logs show:
- `<GHES>` instead of your GHES hostname
- `<ORG>` instead of your organization name

Example: `github.corp.com/myorg/repo#123` becomes `<GHES>/<ORG>/repo#123`

To disable masking (e.g., for debugging), set `GHES_LOGS_MASK=false` in `.kiln/config`.

**Note**: This only applies to GHES configurations. GitHub.com hostnames are not masked.

### 🔥 Run Logs

Each workflow execution creates a dedicated log file for debugging and audit purposes. Logs are stored hierarchically by repository and issue:

```
.kiln/logs/{hostname}/{owner}/{repo}/{issue_number}/{workflow}-{timestamp}.log
```

Example:
```
.kiln/logs/github.com/acme-org/my-repo/42/research-20250121-1430.log
```

**Features:**
- **Per-run isolation**: Each workflow run gets its own log file
- **Session linking**: Companion `.session` files store Claude session IDs for linking to full conversation details
- **Database tracking**: All run metadata (timestamp, outcome, duration) stored in SQLite for querying
- **Reset-safe**: Run logs are preserved when using the `reset` label (debugging history is not deleted)

#### `kiln logs` CLI Command

View run history and logs for a specific issue:

```bash
# List all runs for an issue
kiln logs owner/repo#42

# View a specific log file by run ID
kiln logs owner/repo#42 --view 5

# Get Claude session info for a run
kiln logs owner/repo#42 --session 5
```

**Output example:**
```
Run history for owner/repo#42:

ID     Workflow     Started            Duration     Outcome
----------------------------------------------------------------------
1      research     2025-01-21 10:30   2m 45s       ✓ success
2      plan         2025-01-21 10:35   4m 12s       ✓ success
3      implement    2025-01-21 10:42   running...   ⏳ running

Use 'kiln logs <issue> --view <id>' to view a specific log file.
Use 'kiln logs <issue> --session <id>' to get Claude session info.
```

**Issue identifier formats:**
- `owner/repo#42` — assumes github.com
- `hostname/owner/repo#42` — for GitHub Enterprise Server
