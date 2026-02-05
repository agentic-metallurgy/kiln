# Prepare Implementation (Create Draft PR with Plan)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval
- Do NOT explore the codebase or use Task agents
- Keep it simple and fast

**CRITICAL: DO NOT IMPLEMENT. DO NOT WRITE CODE. DO NOT USE WRITE/EDIT TOOLS. DO NOT MODIFY ANY SOURCE FILES.**

**IT IS NOT YOUR JOB.** There are others who are tasked with those steps.

**Your role is preparation ONLY — creating a draft PR with the plan.** You may:
- Read the GitHub issue
- Create an empty git commit
- Push to remote
- Create a draft PR via `gh`
- Edit the issue description via `gh`

You MUST NOT:
- Write or edit any source files
- Implement any code
- Use Write, Edit, or NotebookEdit tools
- Modify existing code files

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

### Step 2.5: Collapse Plan Section in Issue Description

After extracting the plan, collapse the plan section in the **issue description** to reduce clutter:

1. Get the current issue body:
   ```bash
   gh issue view <issue_url> --json body --jq '.body'
   ```

2. **Collapse the plan section**: If the body contains a plan section (`<!-- kiln:plan -->` ... `<!-- /kiln:plan -->`), wrap it in `<details>` tags:
   ```html
   <details>
   <summary><h2>Implementation Plan</h2></summary>

   <!-- kiln:plan -->
   [existing plan content here]
   <!-- /kiln:plan -->

   </details>
   ```
   **Important**: GitHub requires a blank line after `<summary>` and before `</details>` for markdown to render properly inside.

3. Update the issue description with the collapsed plan:
   ```bash
   gh issue edit <issue_url> --body "..."
   ```

**Note**: The plan stays expanded in the PR body for reference during implementation. Only the issue description gets the collapsed version.

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

### Step 4: Handle Network Errors

If any `gh` command fails, check the error message:

**Network errors (retry these)**:
- `tls handshake timeout`
- `connection refused`
- `connection timeout`
- `error connecting to`
- `i/o timeout`
- `http 5` (covers 500, 502, 503, 504)

**Retry strategy**:
1. Wait 70 seconds (accounts for GitHub ALB TTL ~60s)
2. Retry the command (up to 3 total attempts)
3. Log each retry: `echo "Retrying gh command (attempt X/3) after 70s..."`
4. Only fail after all 3 attempts are exhausted

**Non-network errors (fail immediately)**:
- Authentication errors (`gh auth login`)
- Permission errors (`HTTP 401`, `HTTP 403`)
- Invalid input errors (`GraphQL: Could not resolve`)

### Step 5: Report Completion

```
Done - Draft PR created: <pr_url>
```

ARGUMENTS: $ARGUMENTS
