# Kiln

A polling-based daemon that monitors GitHub Project Kanban boards and orchestrates Claude-powered workflows for software development automation. It enables a human-in-the-loop development process where engineers move issues through kanban columns (Research → Plan → Implement) and Claude handles the execution.

## Requirements

- [`gh` CLI](https://cli.github.com/) installed
- [`claude` CLI](https://docs.anthropic.com/en/docs/claude-code) installed and authenticated
- GitHub PAT (classic) with scopes: `repo`, `project`, `read:org` ONLY (will error out on missing or excessive scopes—**security first**: ONLY least-privilege tokens allowed)
- A GitHub Project Kanban board configured as described below

## Quick Start

### 🔥 Create your GitHub Project Kanban Board

Follow these steps:

1. Create a new GitHub Project
2. Delete all columns except Backlog
3. Run kiln
4. You should click "View" > "Fields" > check "Labels", then "Save View":

<img width="246" height="77" alt="image" src="https://github.com/user-attachments/assets/b051ccf5-02cb-416d-843a-e33963725452" />

5. **Your project board should look like this:**

<img width="640" alt="image" src="https://github.com/user-attachments/assets/04b6952f-7d0b-4ee8-9b94-e4bddfd66554" />


| Column    | What Claude Does                                        | Labels                                  |
|-----------|---------------------------------------------------------|-----------------------------------------|
| Backlog   | —                                                       | —                                       |
| Research  | Explores codebase, writes findings to issue             | researching → research_ready            |
| Plan      | Designs implementation, writes plan to issue            | planning → plan_ready                   |
| Implement | Executes plan, commits code, opens PR, iterates on review | implementing → reviewing → (Validate) |
| Validate  | Nothing; Human review — merge PR when ready             | —                                       |
| Done      | Worktree cleaned up automatically                       | cleaned_up                              |


#### 🔥 Iterative Refinement via Comments

When an issue is in Research or Plan:

1. **You comment** on the issue with feedback or changes
2. **Daemon detects** new comment, adds 👀 reaction
3. **Claude edits** the relevant section (research/plan) in the issue description
4. **Daemon posts** a diff showing what changed
5. **Daemon reacts** 👍 to your comment when done

This lets you iterate, as the human in the loop, on research findings or implementation plans before moving forward.

### 🔥 Run Kiln

```
$ ./run.sh
Using Python: /opt/homebrew/opt/python@3.13/bin/python3.13
Creating virtual environment...
Upgrading pip...
Installing dependencies...

  █▄▀ █ █   █▄ █
  █ █ █ █▄▄ █ ▀█

Created:
  .kiln/
  .kiln/config
  .kiln/logs/
  workspaces/

Next steps:
  1. Edit .kiln/config
  2. Run `kiln` again
```

Edit `.kiln/config`:
- `GITHUB_TOKEN` — your GitHub PAT with scopes: `repo`, `project`, `read:org` ONLY (will error out on missing or excessive scopes—**security first**: ONLY least-privilege tokens allowed)
- `PROJECT_URLS` — project board URLs to monitor (e.g., `https://github.com/orgs/acme-org/projects/1`)
- `ALLOWED_USERNAME` — GitHub username authorized to trigger workflows (so that kiln only acts when YOU do something—CRITICAL)

🔥 Then run `./run.sh` again to start the daemon.

## Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  GitHub Project │────▶│     Daemon      │────▶│   SQLite DB     │
│ (State Machine) │     │    (Poller)     │     │    (Cache)      │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  WorkflowRunner │
                        │  (Orchestrator) │
                        └────────┬────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 ▼               ▼               ▼
           ┌──────────┐    ┌──────────┐    ┌───────────┐
           │ Research │    │   Plan   │    │ Implement │
           │ Workflow │    │ Workflow │    │  Workflow │
           └──────────┘    └──────────┘    └───────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Claude CLI    │
                        │   (Executor)    │
                        └─────────────────┘
```

## Capabilities & Design Decisions

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

### 🔥 Git Worktrees for Parallel Development

Each issue gets an isolated git worktree rather than shared working directory.

- **Parallelism**: Multiple workflows run concurrently without file conflicts
- **Isolation**: Each Claude instance works in its own directory
- **Clean state**: Fresh checkout prevents pollution from previous work
- **Branch per issue**: Natural mapping of issue → branch → worktree

### 🔥 Claude CLI as Execution Engine

Execute workflows via the `claude` CLI rather than direct API calls.

- **Zero auth setup**: Leverages existing `claude` and `gh` logins—no API keys or OAuth flows to configure
- **Commit attribution**: Git commits are attributed to the authenticated user without external auth dependencies
- **Full capabilities**: Claude CLI supports slash commands, tools, file access, and git operations
- **Streaming**: Native support for long-running operations with streaming output

### 🔥 Issue Description as Source of Truth

Research and plan outputs are written and iterated on in the issue description to keep a single source of truth with auditable progression.

- **Single source**: All context in one place for implementation
- **Editable**: Users can directly edit research/plan sections
- **Structured**: HTML markers (`<!-- kiln:research -->`, `<!-- kiln:plan -->`) enable targeted updates
- **Idempotent**: Markers prevent duplicate runs from creating duplicate content

### 🔥 No Comment Iteration at Validation Stage

Comment-based iteration is disabled once work reaches the PR/Validate stage.

- **Prevents bloat**: Stops "vibe coding" via comments that adds unnecessary changes to PRs
- **Token efficiency**: Avoids wasteful back-and-forth on already-implemented work
- **Forces testing**: Developers must checkout the PR locally and test manually
- **Keeps PRs clean**: Fixes are pushed directly rather than AI-appended

**Trade-off**: No comment-driven iteration on PRs. If you prefer not to checkout the branch locally, merge the PR when it's "good enough" and open new issues for remaining fixes.

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
