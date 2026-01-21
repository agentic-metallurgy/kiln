# Kiln

A polling-based daemon that monitors GitHub Project Kanban boards and orchestrates Claude-powered workflows for software development automation. It enables a human-in-the-loop development process where engineers move issues through kanban columns (Research → Plan → Implement) and Claude handles the execution.

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

## Architecture

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

## Capabilities

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

- **Single source**: All context in one place for implementation
- **Editable**: Users can directly edit research/plan sections
- **Structured**: HTML markers (`<!-- kiln:research -->`, `<!-- kiln:plan -->`) enable targeted updates
- **Idempotent**: Markers prevent duplicate runs from creating duplicate content
