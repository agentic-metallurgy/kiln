# Implement GitHub Issue (Single Task Mode)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval

## Execution Flow

### Step 0: Get PR Info

Find the PR for this issue:

```bash
gh pr list --state open --search "closes #<issue_number>" --json number,body,url
```

Then filter results to find the PR that actually contains `Closes #<issue_number>` or `Fixes #<issue_number>` or `Resolves #<issue_number>` in the body (case-insensitive). The search is loose, so you must verify the linking keyword.

**If no matching PR exists**, fail with error: "No PR found. The workflow should have created it."

### Step 1: Find Next Task

1. Parse the PR description for checkbox tasks
2. Find the FIRST unchecked task: `- [ ] <task description>`
3. If all tasks are checked (`- [x]`), report completion and exit

### Step 2: Implement the Task

1. Read the issue for context (research and plan sections)
2. Implement ONLY the identified task
3. Follow existing codebase patterns
4. Write/update tests for the changes
5. Run tests and linting to verify

### Step 3: Mark Task Complete

1. Update the PR description to mark the task as complete:
   - Change `- [ ] <task>` to `- [x] <task>`

2. Use gh to update:
   ```bash
   gh pr edit <pr_number> --body "<updated_body>"
   ```

### Step 4: Commit and Push

1. Stage and commit changes:
   ```bash
   git add -A
   git commit -m "feat: <brief task description>"
   ```

2. Push changes:
   ```bash
   git push
   ```

### Step 5: Exit

After completing one task, exit. The workflow will check progress and call again if needed.

If this was the last task (all tasks now complete), mark PR ready:
```bash
gh pr ready <pr_url>
```

## Output

When done:
```
Completed task: <task description>
Remaining tasks: <count>
```

Or if all complete:
```
All tasks complete - PR ready for review: <pr_url>
```


ARGUMENTS: $ARGUMENTS
