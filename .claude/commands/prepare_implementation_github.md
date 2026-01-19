# Prepare Implementation (Create Draft PR with Plan)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval

## Execution Flow

### Step 1: Read the Issue

1. Read the GitHub issue using `gh issue view <issue_url>`
2. Extract the plan section (between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->`)
3. If no plan section exists, fail with an error message

### Step 2: Create Empty Commit and Draft PR

1. Create an empty commit to establish the PR:
   ```bash
   git commit --allow-empty -m "feat: begin implementation for #<issue_number>"
   ```

2. Push to remote:
   ```bash
   git push -u origin HEAD
   ```

3. Create draft PR with the **entire plan section** as the description:
   ```bash
   gh pr create --draft --title "feat: <issue_title>" --body "$(cat <<'EOF'
   Closes #<issue_number>

   <paste entire plan section here, including all TASKs with their checkboxes>

   ---

   *This PR uses iterative implementation. Tasks are completed one at a time.*
   EOF
   )"
   ```

**Important**: Copy-paste the entire plan section from the issue into the PR body. Do NOT try to extract or reformat tasks - preserve the full plan with all context, file references, and implementation details.

### Step 3: Report Completion

Output:
```
Done - Draft PR created: <pr_url>
```


ARGUMENTS: $ARGUMENTS
