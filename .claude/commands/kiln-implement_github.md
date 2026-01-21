
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

### Step 1: Find Next TASK

The PR description contains **TASKs** (major work blocks) with **subtasks** (checkboxes):

```
## TASK 1: Some major feature
- [ ] Subtask A
- [ ] Subtask B

## TASK 2: Another feature
- [ ] Subtask C
```

1. Parse the PR description and identify all TASKs
2. Find the **first TASK that has any unchecked subtasks**
3. If all subtasks across all TASKs are checked (`- [x]`), report completion and exit

### Step 2: Implement the Entire TASK

Implement **ALL subtasks** under the identified TASK in this single iteration:

1. Read the issue for context (research and plan sections)
2. Use **up to 5 subagents in parallel** to implement subtasks concurrently where possible
3. Follow existing codebase patterns
4. Write/update tests for the changes
5. Run tests and linting to verify ALL changes work together

**Key**: Do not exit after one subtask. Complete the entire TASK block before proceeding.

### Step 3: Mark All Subtasks Complete

1. Update the PR description to mark ALL completed subtasks:
   - Change `- [ ] <subtask>` to `- [x] <subtask>` for each one

2. Use gh to update:
   ```bash
   gh pr edit <pr_number> --body "<updated_body>"
   ```

### Step 4: Commit and Push

1. Stage and commit all changes from the TASK:
   ```bash
   git add -A
   git commit -m "feat: <TASK description>"
   ```

2. Push changes:
   ```bash
   git push
   ```

### Step 5: Exit

After completing one TASK (all its subtasks), exit. The workflow will check progress and call again if more TASKs remain.

If this was the last TASK (all subtasks across all TASKs now complete), mark PR ready:
```bash
gh pr ready <pr_url>
```

## Output

When done:
```
Completed TASK: <TASK description>
Subtasks completed: <count>
Remaining TASKs: <count>
```

Or if all complete:
```
All TASKs complete - PR ready for review: <pr_url>
```


ARGUMENTS: $ARGUMENTS
