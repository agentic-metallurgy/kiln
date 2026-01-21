# Kiln User Guide

Kiln is a GitHub automation daemon that uses Claude to research, plan, and implement issues from your project board.

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

The workflow files are copied to `~/.claude/{commands,agents,skills}`. All kiln files are prefixed with `kiln-` to avoid overwriting your global commands. Kiln never removes existing files.

It will error out until you configure the required fields.

### 2. Create a GitHub Token

Create a **Classic** Personal Access Token (not fine-grained) with exactly these scopes:

| Scope | Purpose |
|-------|---------|
| `repo` | Read/write issues, PRs, and code |
| `project` | Move issues between board columns |
| `read:org` | Read org membership for project access |

⚠️ Kiln validates scopes strictly—missing or extra scopes will error. This is intentional for least privilege.

### 3. Prepare Your Project Board

1. Create a new GitHub Project (board view)
2. Delete all default columns except **Backlog**
3. Run kiln—it creates the remaining columns automatically:
   - Research → Plan → Implement → Validate → Done
4. Show labels on your board: click the **View** settings (next to the query bar), enable "Labels", then **Save** to persist
5. Go to project **Settings** and set a default repository—makes creating issues from the board UI easier

### 4. Configure

Edit `.kiln/config`:

```bash
# Required
GITHUB_TOKEN=ghp_your_token_here
PROJECT_URLS=https://github.com/orgs/your-org/projects/1
ALLOWED_USERNAME=your-github-username

# Optional
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

⚠️ github.com and GHES are mutually exclusive. A single kiln instance cannot connect to both—run separate instances if needed.

---

## 🎯 Your First Issue

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

### Research

**Trigger**: Move issue to Research column

Claude:
1. Reads your issue description
2. Explores the codebase for relevant code
3. Writes findings directly into the issue description

**Output**: Research section added to issue body (wrapped in `<!-- kiln:research -->` markers)

**Next**: Review findings, then move to Plan

### Plan

**Trigger**: Move issue to Plan column

Claude:
1. Uses research findings + issue description
2. Designs a step-by-step implementation plan
3. Writes the plan directly into the issue description

**Output**: Plan section with TASK items added to issue body (wrapped in `<!-- kiln:plan -->` markers)

**Next**: Review plan, then move to Implement

### Implement

**Trigger**: Move issue to Implement column

Claude:
1. Creates a git worktree for the issue
2. Executes each TASK in the plan
3. Commits changes and opens a PR
4. Links the PR to the issue

**Output**: PR ready for review

**Next**: Automatically moves to Validate when done

### Comment Iteration (Research & Plan only)

During Research or Plan, you can leave comments to request changes:

1. Comment on the issue with your feedback
2. Claude edits the relevant section in-place
3. A diff of changes is posted as a reply

Comment iteration is disabled during Implement to keep PRs clean and prevent vibe coding at the end. Checkout the PR branch and do the last mile fix locally.

---

## 🏷️ Special Labels

### `yolo` — Auto-progression

Add this label to let Claude progress through stages autonomously:

| Current Status | With `yolo` |
|---------------|-------------|
| Backlog | Moves to Research immediately |
| Research (when `research_ready`) | Moves to Plan |
| Plan (when `plan_ready`) | Moves to Implement |
| Implement | Moves to Validate when done |

Remove `yolo` at any point to stop auto-progression.

If something goes wrong during yolo mode, the issue gets a `yolo_failed` label.

### `reset` — Clear and Restart

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
