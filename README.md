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

Executes workflows via the Claude Code CLI:

- **No New Auth Setup**: Leverages existing Claude subscription, no trickery
- **Full Claude capabilities**: `/commands`, MCPs, tools, git operations, local file access

### 🔥 Polling Over Webhooks

Use periodic polling instead of webhook-based event handling:

- **Security-first**: No external attack surface, public URLs, webhook secrets management
- **Firewall-friendly**: Works behind VPNs without requiring publicly-accessible endpoints

**Trade-off**: 30-second latency (configurable) vs. near-instant webhook response.

### 🔥 GitHub Labels as Single Source of Truth

Use GitHub labels as the state store:

- **Crash recovery**: Nothing local is sacred, local DB is cache only
- **Visibility**: End to end context is stored as a single artifact, from PRD -> PR
- **Auditability**: Reporting, observability, who did what when are all timestamped along with the commits

### 🔥 Issues to store all context

Research and plan outputs are written and iterated on in the issue to keep a single source of truth with auditable progression. No `.md` files to manage or organize, complete audit trail of which prompts made what edits to the Research/Plan.
