---
name: kiln-create-worktree-from-issues
description: Create git worktree from GitHub issues. Use when user says "create a worktree for issue X" or similar requests involving worktrees and issue numbers.
---

# Create Worktrees from GitHub Issues

Automatically creates git worktrees with semantic branch names for one or more GitHub issues.

## When to Use This Skill

Trigger this skill when the user mentions:
- "worktrees for issues ..."
- "create worktree for issue ..."
- "worktree issue X"
- Any combination of "worktree" and issue numbers

## Instructions

### Step 1: Read Issue Details

The issue details will be in the prompt and begin with "Issue title", "Issue Description"

### Step 2: Generate Branch Name

Create a branch name starting with the issue number:

1. Start with the issue number followed by a hyphen (e.g., `268-`)
2. Take the issue title
3. Summarize it, convert to lowercase
4. Replace spaces and special characters with hyphens
5. Remove consecutive hyphens
6. Truncate the slug to ~32 characters (not counting the issue number prefix)

**Format**: `{issue_number}-{slug}`

Example: Issue #268 "UI theme fixes for contrast issues" -> `268-ui-theme-fixes-for-contrast`

### Step 3: Create Worktree

```bash
git worktree add -b <branch_name> ../quell-ios-issue-<issue_number> main
```

The worktree directory format is always: `../quell-ios-issue-<issue_number>`

### Step 4: Report Results

After processing all issues, report:
- Was the worktrees were created successfully?
- The branch name for each
- The worktree path for each
- Any issues that failed (already exists, etc.)

## Example Output

For "create worktree for issue 81":

```
Successfully created worktree:

| Issue | Branch | Path |
|-------|--------|------|
| #81 | 81-ui-theme-fixes-for-contrast | ../quell-ios-issue-81 |
```

## Error Handling

- If a branch already exists: Skip and report
- If worktree path already exists: Skip and report
- If issue doesn't exist: Report error and continue with others
- If not on main branch initially: Switch to main first