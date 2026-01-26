# Prepare Implementation (Create Draft PR with Plan)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval
- Do NOT explore the codebase or use Task agents
- Keep it simple and fast

## Arguments

This command accepts the following arguments:
- Issue URL (required): The GitHub issue URL
- `--base <branch>` (optional): The base branch for the PR. If specified, the PR will target this branch instead of the default branch. This will be provided when the issue has a parent issue with an open PR.

Example: `/prepare_implementation_github https://github.com/owner/repo/issues/123 --base 5-parent-feature-branch`

## Execution Flow

### Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
1. The issue URL
2. The `--base` flag value (if present) - store this for use in PR creation

### Step 2: Get or Create Plan

Get Issue Content:

```bash
gh issue view <issue_url> --json body,title,number
```

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

Keep it simple in the scenario where there's no plan provided: 2-4 tasks max. Do NOT explore the codebase in-depth.

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

   **If `--base` was provided** (child issue with parent PR):
   ```bash
   gh pr create --draft --base <base_branch> --issue <issue_number> --title "feat: <issue_title>" --body "$(cat <<'EOF'
   Closes #<issue_number>

   > **Note**: This PR targets the branch `<base_branch>`, not the default branch. The issue will auto-close when `<base_branch>` is merged to the default branch, or can be closed manually after this PR merges.

   <plan content here>

   ---

   *This PR uses iterative implementation. Tasks are completed one at a time.*
   EOF
   )"
   ```

   **If `--base` was NOT provided** (standalone issue):

   ```bash
   gh pr create --draft --issue <issue_number> --title "feat: <issue_title>" --body "$(cat <<'EOF'
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
