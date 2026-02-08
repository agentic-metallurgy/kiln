# Kiln Capabilities Map

> A hierarchical view of Kiln's features organized by domain.

## Quick Navigation

- [🔄 Workflow Orchestration](#-workflow-orchestration)
- [🤖 Claude AI Integration](#-claude-ai-integration)
- [🎫 Ticket System Support](#-ticket-system-support)
- [🔌 External Integrations](#-external-integrations)
- [⚙️ Configuration & Operations](#️-configuration--operations)
- [✅ Code Quality & Testing](#-code-quality--testing)
- [Intentional Exclusions](#intentional-exclusions)

## Overview

| Domain | Description | Primary Files |
|--------|-------------|---------------|
| 🔄 Workflow Orchestration | Core daemon, polling, state machine, concurrent execution | `src/daemon.py`, `src/workflows/` |
| 🤖 Claude AI Integration | Commands, agents, skills for Claude Code | `.claude/commands/`, `.claude/agents/`, `.claude/skills/` |
| 🎫 Ticket System Support | GitHub.com and GitHub Enterprise Server | `src/ticket_clients/` |
| 🔌 External Integrations | Slack, MCP, Azure OAuth, credentials | `src/integrations/` |
| ⚙️ Configuration & Operations | Config management, setup, logging | `src/config.py`, `src/setup/`, `src/logger.py` |
| ✅ Code Quality & Testing | Proactive checks, CI, test suite | `scripts/`, `.github/workflows/`, `tests/` |

---

## 🔄 Workflow Orchestration

Core daemon, polling, state machine, and concurrent execution capabilities.

| Capability | Location | Details |
|------------|----------|---------|
| Daemon Polling | `daemon.py:225-261` | Polls GitHub project boards at configurable interval (default 30s) |
| Workflow Pipeline | `workflows/__init__.py` | 5 workflows: Prepare, Research, Plan, Implement, ProcessComments |
| Concurrent Execution | `daemon.py` | Max 6 parallel workflows (configurable) |
| YOLO Mode | `daemon.py:254-261` | Auto-progression through Research → Plan → Implement |
| Stall Detection | `daemon.py` | Detects stuck workflows (>1 hour), clears labels |
| Hibernation Mode | `daemon.py` | Pauses when GitHub API unreachable, 5-minute recovery intervals |
| Reset Workflow | `daemon.py:1575` | Clears kiln content, moves issue to Backlog |
| Comment Processing | `comment_processor.py`, `workflows/process_comments.py` | Processes user comments to edit issue sections in-place |
| Session Resumption | `daemon.py` | Resumes Claude sessions after hibernation or repo relocation |
| Workspace Management | `workspace.py` | Creates/manages git worktrees per issue |
| Worktree Path Collision Fix | `workspace.py` | Uses `owner_repo` format to prevent path collisions |

---

## 🤖 Claude AI Integration

Commands, agents, and skills for Claude Code.

| Capability | Location | Details |
|------------|----------|---------|
| Research Command | `.claude/commands/kiln-research_codebase_github.md` | Spawns parallel sub-agents for codebase research |
| Plan Command | `.claude/commands/kiln-create_plan_github.md` | Creates implementation plans from research |
| Implement Command | `.claude/commands/kiln-implement_github.md` | Implements TASK blocks from PR descriptions |
| Prepare Command | `.claude/commands/kiln-prepare_implementation_github.md` | Creates draft PRs with implementation plans |
| Codebase Analyzer Agent | `.claude/agents/kiln-codebase-analyzer.md` | Analyzes implementation details and data flow |
| Codebase Locator Agent | `.claude/agents/kiln-codebase-locator.md` | Finds files by topic/feature |
| Pattern Finder Agent | `.claude/agents/kiln-codebase-pattern-finder.md` | Finds similar implementations as templates |
| PR Review Agent | `.claude/agents/kiln-pr-review.md` | Reviews PRs against specs |
| Web Search Agent | `.claude/agents/kiln-web-search-researcher.md` | Web research with WebSearch/WebFetch |
| Edit Issue Skill | `.claude/skills/kiln-edit-github-issue-components/` | Edits issue description/research/plan in-place |
| Create Worktree Skill | `.claude/skills/kiln-create-worktree-from-issues/` | Creates worktrees with semantic branch names |
| Model Assignment per Stage | `config.py:94-100` | Haiku for Prepare, Opus for Research/Plan/Implement, Sonnet for ProcessComments |
| Pinned Model Versions | `config.py` | Sonnet and Haiku versions pinned for consistency |

---

## 🎫 Ticket System Support

GitHub.com and GitHub Enterprise Server support.

| Capability | Location | Details |
|------------|----------|---------|
| GitHub.com Client | `ticket_clients/github.py` | Full support for GitHub.com projects |
| GitHub Enterprise 3.14-3.19 | `ticket_clients/github_enterprise_3_*.py` | Version-specific GHES support |
| GHES Auto-Detection | `ticket_clients/` | Automatically detects GHES version |
| TicketClient Protocol | `interfaces/ticket.py` | Abstract protocol for ticket system integrations (protocol only) |
| Label Management | `labels.py` | 14 labels for workflow states, control, failure |
| Comment Reactions | `ticket_clients/base.py` | Eyes (processing) and thumbs-up (complete) markers |
| PR Linking | `ticket_clients/base.py` | Query and manage linked pull requests |
| Board Column Management | `ticket_clients/` | Handles GitHub default kanban columns |
| Feature Branch Support | Issue frontmatter | `feature_branch` frontmatter for custom base branches |
| Blocked By Dependencies | Issue frontmatter | `blocked_by` issue setting for merge queue |
| Sub-Issue Support | `interfaces/ticket.py` | Parent/child issue relationships |
| Status Actor Audit | `security/authorization.py` | Tracks who changed project status |

---

## 🔌 External Integrations

Slack, MCP, Azure OAuth, and credentials management.

| Capability | Location | Details |
|------------|----------|---------|
| Slack Notifications | `integrations/slack.py` | DM notifications for phase completion, PR creation, validation ready |
| Slack Comment Processing DM | `integrations/slack.py` | Notifies when user comments are processed |
| MCP Server Support | `integrations/mcp_client.py` | Test connectivity to MCP servers (stdio and HTTP/SSE) |
| MCP Bearer Token Auth | `integrations/mcp_client.py` | Bearer token substitution for authenticated MCPs |
| Azure OAuth 2.0 | `integrations/azure_oauth.py` | ROPC flow for Azure Entra ID MCP auth |
| Repository Credentials | `integrations/repo_credentials.py` | YAML-based credential injection for integration testing |
| Git Credential Helper | `setup/` | Auto-configures git credential helper for HTTPS auth |
| Git Credential Cleanup | `setup/` | Cleans up credential helper on uninstall |
| OpenTelemetry Tracing | `integrations/telemetry.py` | Metrics and tracing support |

---

## ⚙️ Configuration & Operations

Config management, setup, and logging.

| Capability | Location | Details |
|------------|----------|---------|
| YAML/Env Config Loaders | `config.py:231-625` | Load from `.kiln/config` or environment variables |
| Config Validation | `config.py` | 50+ configuration variables with validation |
| Startup Health Checks | `setup/checks.py` | Validates Claude CLI, git, dependencies |
| Missing Config Warnings | `config.py` | Lists missing config variables on startup |
| Brew Version Check | `setup/` | Checks for brew updates on startup |
| GHES Log Masking | `config.py` | Masks hostname/org names in logs (configurable) |
| Run History Logging | `cli.py`, `database.py` | `kiln logs` command with session tracking |
| Log Simplification | `cli.py` | Simplified log viewing commands |
| Daemon Mode | `cli.py` | `--daemon` flag for background operation |
| Home Directory Check | `cli.py` | Refuses to run in user home directory |

---

## ✅ Code Quality & Testing

Proactive checks, CI, and test suite.

| Capability | Location | Details |
|------------|----------|---------|
| Config Sync Check | `scripts/check_config_sync.py` | Detects drift between `.env.example` and `config.py` |
| Orphan Module Detection | `scripts/check_orphan_modules.py` | Finds Python files not reachable from entry points |
| Vulture Dead Code Check | `.github/workflows/vulture-check.yml` | Blocking CI check for unused code |
| Proactive Checks CI | `docs/workflows/proactive-checks.yml` | CI workflow for config sync and orphans |
| Test Coverage Enforcement | `pytest.ini` | 80% coverage requirement |
| Mutation Testing | `pyproject.toml` | mutmut integration |
| Property-Based Testing | `tests/` | Hypothesis integration |
| Protocol Conformance Tests | `tests/` | Tests for TicketClient implementations |
| CI on Push/PR | `.github/workflows/` | Runs tests on push/PR |
| CodeQL Security Scanning | `.github/workflows/` | All CodeQL alerts remediated |
| Ruff Enforcement | `.github/workflows/` | Ruff linting in CI |
| Dependabot | `.github/dependabot.yml` | Automated dependency updates |

---

## Intentional Exclusions

What we chose NOT to build, and why.

| Exclusion | Reason | Reference |
|-----------|--------|-----------|
| No Webhooks | Security-first design; polling works behind firewalls with no external attack surface | Design principle |
| No PagerDuty | Removed - complexity not justified for daemon workload | Removed in PR #207 |
| No Jira/Linear Implementation | Protocol documented but not implemented; focused on GitHub first | `interfaces/README.md` |
| No Production Coverage Tracking | Deferred; 80% test coverage sufficient for daemon | Backlog |
| No Fine-Grained Access Tokens | Planned but not yet implemented | Issue #203 |
| No Other Coding CLIs | Focused on Claude Code only | Closed as won't-do |
| No Circular Dependency Detection | Causes immediate runtime failures, self-correcting | By design |
| No Dependency Graphing/Visualization | Not prioritized | Issue #183 |
| No Automated Email from GitHub Actions | Under research | Issue #247 |
| No Interactive Setup | Planned but not implemented | Issue #192 |
| No Automated Issue Closing | Requires human actor | Issue #221 |
| No Debug Command | Planned for failure analysis | Issue #220 |
| No BDD-Style Tests | Under research | Issue #150 |
| No MCP Config Validation | Planned startup validation | Issue #252 |
| No Dependabot PR Auto-Merge | Planned automation | Issue #264 |

---

## Reference

### Workflow State Machine Labels

| Label | Type | Purpose |
|-------|------|---------|
| `preparing` | Running | Prepare workflow in progress |
| `researching` | Running | Research workflow in progress |
| `planning` | Running | Plan workflow in progress |
| `implementing` | Running | Implement workflow in progress |
| `reviewing` | Running | PR under internal review |
| `editing` | Running | Processing user comment |
| `research_ready` | Complete | Research workflow completed |
| `plan_ready` | Complete | Plan workflow completed |
| `cleaned_up` | State | Worktree has been cleaned up |
| `yolo` | Control | Auto-progress through Research → Plan → Implement |
| `yolo_failed` | Failure | YOLO auto-progression failed |
| `reset` | Control | Clear kiln content and move issue to Backlog |
| `implementation_failed` | Failure | Implementation workflow failed |
| `research_failed` | Failure | Research completed but no research block found |

### Project Board Status Flow

```
Backlog → Research → Plan → Implement → Validate → Done
          ↑                     │
          └────── reset ────────┘
```

### Issue Frontmatter Fields

```yaml
feature_branch: my-feature   # Base branch for worktree
blocked_by: owner/repo#123   # Dependency for merge queue
```
