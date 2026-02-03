# Kiln

Kiln orchestrates Claude Code instances on your local machine using GitHub projects as its control panel.

When you move issues from one column to another, Kiln invokes Claude to run the corresponding `/command`.

Claude creates the worktrees, researches the codebase, creates and implements the plan.

It's designed to be simple, requires very little setup:

- **Use your existing Claude subscription** (no auth trickery, no API keys needed, runs locally)
- **All context and state is on GitHub** (no markdown mess, no local DBs, easy recovery)
- **Poll instead of webhooks/events** (no external attack surfaces, works behind VPN)
- **Supports MCPs and anything else Claude can do**

That's the heart of it and it works because… it's Claude :)

## What it looks like

![Research and Plan demo](https://media.githubusercontent.com/media/agentic-metallurgy/kiln-docs/main/src/assets/research-and-plan-1080p-30fps.gif)

(sorry for the large gif)

| ⚪ Backlog | 🔵 Research | 🟣 Plan | 🟠 Implement | 🟡 Validate | 🟢 Done |
|-----------|-------------|---------|--------------|-------------|---------|
| *new issues* | *codebase exploration* | *design tasks* | *write code* | *human review* | *complete* |

## Installation and How-To

See https://kiln.bot/docs

## Design Principles

### 🔥 Claude CLI as Execution Engine

Executes workflows via the Claude Code CLI:

- **No New Auth Setup**: Leverages existing Claude subscription, no trickery
- **Full Claude capabilities**: `/commands`, MCPs, tools, git operations, local file access

### 🔥 GitHub as Single Source of Truth

Uses GitHub as the end-to-end context and state store:

- **Single source of truth**: Research and plan outputs are written and iterated on in the issue
- **Crash recovery**: Nothing local is sacred, local DB is cache only
- **Visibility**: End to end context is stored as a single artifact, from PRD -> PR
- **Observability**: Issue to PR to Merge all timestamped, easy to derive analytics
- **No `.md` mess**: No local files to manage and organize, see which prompts made what edits to research and plan

### 🔥 Polling Over Webhooks

Use periodic polling instead of webhook-based event handling:

- **Security-first**: No external attack surface, public URLs, webhook secrets management
- **Firewall-friendly**: Works behind VPNs without requiring publicly-accessible endpoints

**Trade-off**: 30-second latency (configurable) vs. near-instant webhook response.

## Documentation

https://kiln.bot/docs
