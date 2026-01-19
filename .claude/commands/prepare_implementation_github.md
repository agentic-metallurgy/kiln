# Prepare Implementation (Create Draft PR with Plan)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval
- Do NOT explore the codebase or use Task agents
- Keep it simple and fast

## Execution Flow

### Step 1: Get Issue Content

```bash
gh issue view <issue_url> --json body,title,number
```

### Step 2: Get or Create Plan

Check for plan section (between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->`):

**If plan exists**: Extract it for use in the PR.

**If NO plan exists**: Create a simple plan based on the issue title and description:

```markdown
## Implementation Plan

**Goal:** [One sentence from issue title]

**Approach:** [2-3 sentences based on issue description]

---

### TASK 1: [First logical step]
**Milestone:** [Verifiable outcome]

- [ ] Subtask 1
- [ ] Subtask 2

### TASK 2: [Second logical step]
**Milestone:** [Verifiable outcome]

- [ ] Subtask 1
- [ ] Subtask 2

---

### Verification
- [ ] All changes tested
- [ ] Code follows existing patterns
```

Keep it simple - 2-4 tasks max. Do NOT explore the codebase.

### Step 3: Create Empty Commit and Draft PR

1. Create an empty commit:
   ```bash
   git commit --allow-empty -m "feat: begin implementation for #<issue_number>"
   ```

2. Push to remote:
   ```bash
   git push -u origin HEAD
   ```

3. Create draft PR with the plan:
   ```bash
   gh pr create --draft --title "feat: <issue_title>" --body "$(cat <<'EOF'
   Closes #<issue_number>

   <plan content here>

   ---

   *This PR uses iterative implementation. Tasks are completed one at a time.*
   EOF
   )"
   ```

### Step 4: Report Completion

```
Done - Draft PR created: <pr_url>
```

ARGUMENTS: $ARGUMENTS
