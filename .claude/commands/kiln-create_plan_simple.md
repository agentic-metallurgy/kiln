# Create Simple Plan (Fallback for Direct-to-Implement)

You are running in **headless, non-interactive mode** as part of an automated workflow.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT ask clarifying questions
- Do NOT wait for user approval
- Do NOT explore the codebase or use Task/Explore agents
- Do NOT read any files other than the issue
- Just create a simple plan from the issue text alone

**CRITICAL: DO NOT IMPLEMENT. DO NOT WRITE CODE. DO NOT USE WRITE/EDIT TOOLS. DO NOT MODIFY ANY SOURCE FILES.**

**IT IS NOT YOUR JOB.** There are others who are tasked with those steps.

**Your role is planning ONLY.** You may:
- Read the GitHub issue
- Post the plan to the GitHub issue (via `gh issue edit`)

You MUST NOT:
- Write or edit any source files
- Modify any code
- Create new files (except via `gh` for issue editing)
- Use Write, Edit, or NotebookEdit tools
- Make git commits or push changes
- Explore the codebase or spawn sub-agents

## Context

This command creates a quick, minimal plan when an issue goes directly to Implement without a formal plan. Keep it simple and fast.

## Execution Flow

### Step 1: Read the Issue

```bash
gh issue view <issue_url> --json title,body
```

### Step 2: Check for Research (in the issue body only)

Look for research section (between `<!-- kiln:research -->` and `<!-- /kiln:research -->`) **in the issue body you just fetched**.

- **If research exists in the body**: Use those findings to inform your plan
- **If no research**: Use just the issue title and description

**DO NOT** explore the codebase, read files, or do any additional research. Work only with what's in the issue.

### Step 3: Create a Simple Plan

Based on available context (research if present, otherwise just issue), create a plan with:
- Clear, verifiable milestones
- Checkbox tasks that can be tracked
- Focus on what needs to be done, not extensive analysis

**Plan Format:**

```markdown
## Implementation Plan

**Goal:** [One sentence summary from issue title]

**Approach:** [2-3 sentences on how to achieve this based on issue description]

---

### TASK 1: [First logical step]
**Milestone:** [What completing this achieves - verifiable outcome]

- [ ] Subtask 1
- [ ] Subtask 2

### TASK 2: [Second logical step]
**Milestone:** [What completing this achieves - verifiable outcome]

- [ ] Subtask 1
- [ ] Subtask 2

[Add more tasks as needed - keep it focused, typically 2-4 tasks]

---

### Verification
- [ ] All changes tested
- [ ] Code follows existing patterns
```

**Guidelines:**
- Keep tasks focused and achievable
- Each task should have a clear, verifiable milestone
- Don't over-engineer - this is a simple plan for straightforward issues
- If the issue is complex, create tasks for the obvious first steps
- If research exists, reference specific files/patterns discovered
- Include a verification task at the end

### Step 4: Write Plan to Issue

Update the issue description to add the plan in a kiln:plan section:

```bash
gh issue edit <issue_number> --repo <repo> --body "<updated body with plan>"
```

The updated body should:
1. Keep the original issue content
2. Add the plan wrapped in `<!-- kiln:plan -->` and `<!-- /kiln:plan -->` markers

### Step 5: Output Confirmation

```
Done - Simple plan added to issue #<number>
```

ARGUMENTS: $ARGUMENTS
