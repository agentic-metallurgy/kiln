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

## What it looks like

![Research and Plan demo](https://media.githubusercontent.com/media/agentic-metallurgy/kiln-docs/main/src/assets/research-and-plan-1080p-30fps.gif)

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

## Installation and How-To

See https://kiln.bot/docs

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
