# Implement GitHub Issue

You are running in **headless, non-interactive mode** as part of an automated workflow. Complete the entire implementation process autonomously.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval
- Do NOT present options for the user to choose from

## Execution Flow

### Step 0: Check if Already Done

If the implementation has already happened and the PR was created, skip all steps and report completion.

### Step 1: Read the Issue Completely

1. Read the GitHub issue using `gh issue view <issue_url>`
2. Understand the spec from the structured sections in the issue to implement (in order of preference):
   - If both the Research section (between `<!-- kiln:research -->` and `<!-- /kiln:research -->`) AND the Plan section (between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->`) exist: Use the Plan section to implement, refer to the Research as needed for deeper understanding of why; Ignore the original issue description as it may contain outdated context that has been refined.
   - **Important**: If a Plan OR Research section exists, use ONLY those sections as the spec. Ignore the original issue description as it may contain outdated context that has been refined during research/planning.
   - If neither research nor plan exists: Use the original issue description to support direct-to-Implement or YOLO workflows.
3. User feedback has already been applied to the research and plan sections
4. If you encounter conflicting guidance, resolve it using this precedence order (transitive): Plan > Research > original issue description.

### Step 2: Implement

1. Rebase from the base branch before starting:
   - If a "Parent branch" is specified in the arguments, rebase from that parent branch
   - Otherwise, rebase from main branch
2. Implement the changes as described in the spec, using the sections in order of preference described above.
3. Follow existing codebase patterns
4. Write/update tests for new behavior
5. Run tests and linting to verify

### Step 3: Create Draft PR

1. Commit and push to the feature branch
2. Create a **DRAFT PR** with description that closes the issue:
   ```bash
   gh pr create --draft --title "<title>" --base <base_branch> --body "<body with Closes #N>"
   ```
   - If a "Parent branch" is specified in the arguments, use `--base <parent_branch>` to target the parent's branch
   - Otherwise, omit `--base` to target the default branch (main)
   - If reviewers are specified, add them with `--reviewer` flags
3. Save the PR URL for the review loop

### Step 4: Review Loop (max 3 iterations)

You're going to ask a pr-review agent to validate your work up to 3 times if needed.

First, add the `reviewing` label to the issue to indicate we've reached the review stage:
```bash
gh issue edit <issue_number> --repo <owner/repo> --add-label reviewing
```

For each iteration:

1. **Call the @pr-review agent** with the PR URL
2. Wait for the agent to complete its work.
3. **If APPROVED**: Exit loop, proceed to Step 5
4. **If CHANGES_REQUESTED**:
   - Read the review comments from the PR using `gh pr view <pr_url> --json reviews,comments`
   - Fix the issues identified in the code
   - Run tests to verify fixes pass
   - Stage and commit the fixes:
     ```bash
     git add -A && git commit -m "Address PR review feedback (iteration N)"
     ```
   - Push the commits so the pr-review agent sees them:
     ```bash
     git push
     ```
   - Continue to next iteration

After max iterations, proceed to Step 5 anyway.

Remove the `reviewing` label now that the review stage is complete:
```bash
gh issue edit <issue_number> --repo <owner/repo> --remove-label reviewing
```

### Step 5: Mark PR Ready for Review

Convert the draft PR to ready for review:
```bash
gh pr ready <pr_url>
```

### Step 6: Notify on Issue

Post a comment to the issue with:
- Very short bullet list of what's been done
- Link to the PR
- Number of review iterations completed

## Output

When done:
```
Done - PR created: <pr_url>
Review iterations: <N>
```
