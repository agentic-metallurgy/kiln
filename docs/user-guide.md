# Kiln User Guide

🎯 ← these indicate deliberate design decisions that may be unexpected at first, usually made due to limitations.

Kiln is a GitHub automation daemon that uses Claude to research, plan, and implement issues from your project board.

---

- [Setup](#-setup)
- [Your First Issue](#-your-first-issue)
- [Workflows](#️-workflows)
- [Special Labels](#️-special-labels)
- [Quick Reference](#-quick-reference)

---

## 🔧 Setup

### 1. Install

```bash
brew tap agentic-metallurgy/tap
brew install kiln
```

Then create a dedicated folder and start kiln:

```bash
mkdir kiln
cd kiln
kiln
```

Kiln creates files in the current directory—don't run it in your home folder.

On first run, kiln creates:
- `.kiln/config` — configuration file (you'll edit this next)
- `.kiln/logs/` — log files
- `.kiln/commands/`, `.kiln/agents/`, `.kiln/skills/` — Claude workflow files
- `workspaces/` — git worktrees for implementation

🎯 The workflow files are copied to `~/.claude/{commands,agents,skills}`. All kiln files are prefixed with `kiln-` to avoid overwriting your global commands. Kiln never removes existing files.

It will error out until you configure the required fields.

### 2. Create a GitHub Token

Create a **Classic** Personal Access Token (not fine-grained) with exactly these scopes:

| Scope | Purpose |
|-------|---------|
| `repo` | Read/write issues, PRs, and code |
| `project` | Move issues between board columns |
| `read:org` | Read org membership for project access |

⚠️🎯 Kiln validates scopes strictly—missing or extra scopes will error. This is intentional for least privilege.

### 3. Prepare Your Project Board

1. Create a new GitHub Project (board view)
2. Delete all default columns except **Backlog**
3. Run kiln—it creates the remaining columns automatically
4. Show labels on your board: click the **View** settings (next to the query bar), enable "Labels", then **Save** to persist
5. Go to project **Settings** and set a default repository—makes creating issues from the board UI easier

Your board should look like this:

| ⚪ Backlog | 🔵 Research | 🟣 Plan | 🟠 Implement | 🟡 Validate | 🟢 Done |
|-----------|-------------|---------|--------------|-------------|---------|
| *new issues* | *codebase exploration* | *design tasks* | *write code* | *human review* | *complete* |

### 4. Configure

Edit `.kiln/config`:

```bash
# Required
GITHUB_TOKEN=ghp_your_token_here
PROJECT_URLS=https://github.com/orgs/your-org/projects/1
USERNAME_SELF=your-github-username

# Optional
USERNAMES_TEAM=teammate1,teammate2
POLL_INTERVAL=30
MAX_CONCURRENT_WORKFLOWS=3
LOG_LEVEL=INFO
```

**GitHub Enterprise Server** — replace `GITHUB_TOKEN` with:

```bash
GITHUB_ENTERPRISE_HOST=github.mycompany.com
GITHUB_ENTERPRISE_TOKEN=ghp_your_token_here
GITHUB_ENTERPRISE_VERSION=3.19
```

⚠️🎯 github.com and GHES are mutually exclusive. A single kiln instance cannot connect to both—run separate instances if needed.

---

## 🔌 MCP Server Configuration

MCP (Model Context Protocol) servers give Claude access to external tools during workflow execution—deployment APIs, monitoring systems, databases, and more. Kiln supports both local MCP servers (stdio) and remote MCP servers (HTTP/SSE), including those that require Azure Entra ID (Azure AD) authentication.

### How It Works

1. Define MCP servers in `.kiln/mcp.json`
2. Configure Azure OAuth credentials in `.kiln/config` (if servers need authentication)
3. At startup, Kiln tests connectivity to each MCP server and lists available tools
4. Kiln retrieves bearer tokens and writes resolved config to each worktree
5. Claude workflows receive the `--mcp-config` flag and can use your MCP tools

### MCP Config Structure

Create `.kiln/mcp.json` in your kiln directory:

```json
{
  "mcpServers": {
    "deployment-api": {
      "command": "npx",
      "args": ["-y", "@company/mcp-deployment-server"],
      "env": {
        "API_ENDPOINT": "https://deploy.company.com",
        "BEARER_TOKEN": "${AZURE_BEARER_TOKEN}"
      }
    },
    "monitoring": {
      "command": "python",
      "args": ["-m", "monitoring_mcp"],
      "env": {
        "AUTH_TOKEN": "${AZURE_BEARER_TOKEN}",
        "REGION": "us-east-1"
      }
    }
  }
}
```

**Local server entries** require:
- `command`: Executable to run
- `args`: Array of command arguments
- `env` (optional): Environment variables for the server process

**Remote server entries** (HTTP/SSE) require:
- `url`: The HTTP endpoint for the MCP server
- `env` (optional): Environment variables (can include auth tokens)

Example remote MCP server:

```json
{
  "mcpServers": {
    "jenkins-api": {
      "url": "https://jenkins.company.com/mcp",
      "env": {
        "AUTHORIZATION": "Bearer ${AZURE_BEARER_TOKEN}"
      }
    }
  }
}
```

### Token Placeholders

Kiln supports the following placeholder for dynamic token substitution:

| Placeholder | Description |
|-------------|-------------|
| `${AZURE_BEARER_TOKEN}` | Azure OAuth 2.0 bearer token from ROPC flow |

The placeholder can be used in any string field within your MCP config—typically in `env` values for authentication headers or tokens.

### Startup Logging

At daemon startup, Kiln tests connectivity to each configured MCP server and logs the results. This helps verify your MCP configuration is working correctly.

**Successful connections:**
```
MCP configuration loaded with 2 server(s)
  deployment-api MCP loaded successfully. Tools: deploy_app, rollback, get_status
  monitoring MCP loaded successfully. Tools: get_metrics, list_alerts, acknowledge_alert
```

**Connection failures:**
```
MCP configuration loaded with 2 server(s)
  deployment-api MCP: connection failed (timeout after 30s)
  monitoring MCP loaded successfully. Tools: get_metrics, list_alerts, acknowledge_alert
```

**Connection timeout behavior:**
- Default timeout is 30 seconds per server
- All servers are tested in parallel for efficiency
- Connection failures are logged as warnings but **do not prevent daemon startup**
- If a server fails to connect at startup, Claude may still attempt to use it during workflows

🎯 Connection testing is informational only. A server that fails the startup test might still work later (e.g., if it was temporarily unavailable).

### Azure OAuth Setup

To use `${AZURE_BEARER_TOKEN}`, configure Azure credentials in `.kiln/config`:

```bash
# Azure Entra ID (Azure AD) credentials for MCP authentication
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_ID=your-client-id
AZURE_USERNAME=service-user@yourdomain.com
AZURE_PASSWORD=your-service-user-password

# Optional: Custom OAuth scope (defaults to Microsoft Graph)
# AZURE_SCOPE=api://your-api/.default
```

**Requirements:**
- All Azure fields must be set together or none at all
- The Azure AD application must allow ROPC (Resource Owner Password Credentials) flow
- The service user account must have appropriate permissions

**Setting up Azure AD:**
1. Create an Azure AD application in your Azure portal
2. Enable "Allow public client flows" in Authentication settings
3. Create a service user account (e.g., `kiln-service@yourdomain.com`)
4. Grant the service user necessary API permissions
5. Configure the fields above with your credentials

### Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| "MCP config contains placeholder but no Azure OAuth client is configured" | Using `${AZURE_BEARER_TOKEN}` without Azure credentials | Add Azure OAuth fields to `.kiln/config` |
| "All Azure OAuth fields must be set together or none" | Partial Azure configuration | Ensure all five fields are set: `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_USERNAME`, `AZURE_PASSWORD` |
| "Token request failed: AADSTS..." | Azure authentication error | Check credentials, verify ROPC is enabled, confirm user permissions |
| "Invalid JSON in MCP config file" | Malformed `.kiln/mcp.json` | Validate JSON syntax (check for trailing commas, missing quotes) |
| "MCP server 'X' is missing 'command' field (local server)" | Incomplete local server definition | Local servers need a `command` field; remote servers need a `url` field |
| MCP server not receiving token | Placeholder typo | Ensure exact match: `${AZURE_BEARER_TOKEN}` (case-sensitive) |

**Token behavior:**
- Tokens are cached and proactively refreshed 5 minutes before expiry
- If token retrieval fails, Kiln logs a warning and continues without substitution
- Each worktree gets its own resolved MCP config at `.mcp.kiln.json`

🎯 MCP config is optional. If `.kiln/mcp.json` doesn't exist, workflows run without MCP tools.

---

## 🚀 Your First Issue

### Where to Create

Create issues directly in the project board UI (preferred). Click **+ Add item** in any column.

You can start from any column: Backlog, Research, Plan, or even Implement. Kiln picks up wherever you drop it.

### Status Progression

| Status | What Happens |
|--------|--------------|
| **Research** | Claude explores the codebase and writes findings to the issue |
| **Plan** | Claude designs an implementation plan and writes it to the issue |
| **Implement** | Claude executes the plan, commits code, and opens a PR |
| **Validate** | You review the PR (Claude does nothing here) |
| **Done** | Worktree is cleaned up |

### What to Expect

Each workflow adds labels to show progress:

| Status | Running | Complete |
|--------|---------|----------|
| Research | `researching` | `research_ready` |
| Plan | `planning` | `plan_ready` |
| Implement | `implementing` | (moves to Validate) |

---

## ⚙️ Workflows

### 🔵 Research

**Trigger**: Move issue to Research column

Claude:
1. Reads your issue description
2. Explores the codebase for relevant code
3. Writes findings directly into the issue description

**Output**: Research section added to issue body (wrapped in `<!-- kiln:research -->` markers)

**Next**: Review findings, then move to Plan

### 🟣 Plan

**Trigger**: Move issue to Plan column

Claude:
1. Uses research findings + issue description
2. Designs a step-by-step implementation plan
3. Writes the plan directly into the issue description

**Output**: Plan section with TASK items added to issue body (wrapped in `<!-- kiln:plan -->` markers)

**Next**: Review plan, then move to Implement

### 🟠 Implement

**Trigger**: Move issue to Implement column

Claude:
1. Creates a git worktree for the issue
2. Executes TASKs in a ralph loop, one at a time (max iterations = number of TASKs, with failsafes to catch infinite loops)
3. Commits changes and opens a PR
4. Links the PR to the issue

**Output**: PR ready for review

**Next**: Automatically moves to Validate when done

### 🔄 Comment Iteration (Research & Plan only)

During Research or Plan, you can leave comments to request changes:

1. Comment on the issue with your feedback
2. Claude edits the relevant section in-place
3. A diff of changes is posted as a reply

🎯 Comment iteration is disabled during Implement to keep PRs clean and prevent vibe coding at the end. Checkout the PR branch and do the last mile fix locally.

---

## 🏷️ Special Labels

### 🤖 `yolo` — Auto-progression

Add this label to let Claude progress through stages autonomously:

| Current Status | With `yolo` |
|---------------|-------------|
| Backlog | Moves to Research immediately |
| Research (when `research_ready`) | Moves to Plan |
| Plan (when `plan_ready`) | Moves to Implement |
| Implement | Moves to Validate when done |

Remove `yolo` at any point to stop auto-progression.

If something goes wrong during yolo mode, the issue gets a `yolo_failed` label.

### 💥 `reset` — Clear and Restart

Add this label to wipe kiln-generated content and start fresh:

1. Closes any open PRs for the issue
2. Deletes PR branches
3. Removes research and plan sections from issue body
4. Removes all labels
5. Moves issue back to Backlog

Useful when you want to completely redo an issue.

---

## 📋 Quick Reference

| Action | How |
|--------|-----|
| Start a workflow | Move issue to Research (or any status) |
| Progress manually | Move issue to next column |
| Progress automatically | Add `yolo` label |
| Request changes | Comment on issue (Research/Plan only) |
| Start over | Add `reset` label |
| Stop auto-progression | Remove `yolo` label |

| Label | Meaning |
|-------|---------|
| `researching` / `planning` / `implementing` | Workflow running |
| `research_ready` / `plan_ready` | Workflow complete, ready to advance |
| `reviewing` | PR under internal review |
| `yolo` | Auto-progress enabled |
| `reset` | Clear content and restart |
| `implementation_failed` | Implementation failed after retries |
