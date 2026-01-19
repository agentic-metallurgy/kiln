# Prepare Implementation (Create Draft PR with Task List)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval

## Execution Flow

### Step 1: Read the Issue

1. Read the GitHub issue using `gh issue view <issue_url>`
2. Extract the plan section (between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->`)
3. If no plan section exists, fail with an error message

### Step 2: Extract Task List

From the plan, extract all actionable tasks. Look for:
- Checkboxes: `- [ ] Task description`
- Numbered items under "Changes Required" or similar headers
- Phase summaries with specific implementation steps

Create a flat checkbox list of all tasks in the order they should be executed.

**Example output format:**
```markdown
## Implementation Tasks

- [ ] Add new fields to IssueState dataclass in src/database.py
- [ ] Add database migration for new columns
- [ ] Create PrepareImplementationWorkflow class
- [ ] Add label constant to Labels class
- [ ] Update WORKFLOW_MAP in daemon.py
- [ ] Run tests and fix any failures
```

### Step 3: Create Empty Commit and Draft PR

1. Create an empty commit to establish the PR:
   ```bash
   git commit --allow-empty -m "feat: begin implementation for #<issue_number>"
   ```

2. Push to remote:
   ```bash
   git push -u origin HEAD
   ```

3. Create draft PR with task list as description:
   ```bash
   gh pr create --draft --title "feat: <issue_title>" --body "$(cat <<'EOF'
   Closes #<issue_number>

   ## Implementation Tasks

   - [ ] Task 1
   - [ ] Task 2
   ...

   ---

   *This PR uses iterative implementation. Tasks are completed one at a time.*
   EOF
   )"
   ```

### Step 4: Report Completion

Output:
```
Done - Draft PR created: <pr_url>
Tasks extracted: <count>
```


ARGUMENTS: $ARGUMENTS
