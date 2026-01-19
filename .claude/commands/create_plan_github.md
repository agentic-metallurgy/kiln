# GitHub Issue Implementation Plan (Headless/Automated)

You are running in **headless, non-interactive mode** as part of an automated workflow. You MUST complete the entire planning process autonomously without asking questions or waiting for user input.

**CRITICAL**: This is an automated pipeline, so:
- Do NOT Ask clarifying questions
- Do NOT Wait for user approval
- Do NOT Present options for the user to choose from
- Do NOT Request feedback before proceeding

## Execution Flow

When this command is invoked with a GitHub issue reference:

### Step 1: Read the Issue

1. Read the GitHub issue using `gh`:
   ```bash
   GH_HOST=<hostname> gh issue view https://<hostname>/<owner>/<repo>/issues/<num>
   ```

2. If a research section exists (`<!-- kiln:research -->`), use it as context
3. Understand the requirements and constraints

### Step 2: Context Gathering & Research

1. **Read all mentioned files immediately and FULLY**:
   - Issue description references
   - Research documents linked
   - Any JSON/data files mentioned
   - **IMPORTANT**: Use the Read tool WITHOUT limit/offset parameters to read entire files
   - **CRITICAL**: DO NOT spawn sub-tasks before reading these files yourself in the main context
   - **NEVER** read files partially - if a file is mentioned, read it completely

2. **Spawn parallel research tasks** to gather context:
   - Use **codebase-locator** agent to find all files related to the issue
   - Use **codebase-analyzer** agent to understand current implementation
   - Use **codebase-pattern-finder** agent to find similar features to model after

   These agents will:
   - Find relevant source files, configs, and tests
   - Trace data flow and key functions
   - Return detailed explanations with file:line references

3. **Read all files identified by research tasks**:
   - After research tasks complete, read ALL files they identified as relevant
   - Read them FULLY into the main context
   - This ensures you have complete understanding before proceeding

4. **Analyze and verify understanding**:
   - Cross-reference the issue requirements with actual code
   - Identify existing patterns to follow
   - Determine the implementation approach based on codebase conventions
   - Note any assumptions you're making

### Step 3: Create and Post the Plan

- If the research states a selected approach (e.g., "Selected: X" or a specific recommended solution), follow that decision / solution path.
- Only make autonomous decisions for unresolved questions. 
- When multiple approaches exist, do not ask for input, choose the one that: Best matches existing codebase patterns, is simplest to implement, and has the clearest path forward to addressing the issue as defined.

**Post the plan directly to the issue description**:
1. Get the current body using `gh` (NOT REST API, NOT curl):
   ```bash
   gh issue view https://<hostname>/<owner>/<repo>/issues/<num> --json body --jq '.body'
   ```
2. **Collapse the research section**: If the body contains a research section (`<!-- kiln:research -->` ... `<!-- /kiln:research -->`), wrap it in `<details>` tags to collapse it now that the plan is being written:
   ```html
   <details>
   <summary><h2>Research Findings</h2></summary>

   [existing research content here]

   </details>
   ```
   **Important**: GitHub requires a blank line after `<summary>` and before `</details>` for markdown to render properly inside.
3. Append the plan section with proper markers
4. Update using `gh` (NOT REST API, NOT curl):
   ```bash
   gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."
   ```

The plan section MUST:
- Start with `---` separator
- Be wrapped in `<!-- kiln:plan -->` and `<!-- /kiln:plan -->` markers
- Preserve all existing content in the description (with research now collapsed)

## Plan Template

````markdown
---
<!-- kiln:plan -->
# [Feature/Task Name] Implementation Plan

## Overview

[Brief description of what we're implementing and why]

## Current State Analysis

[What exists now, what's missing, key constraints discovered]

## Desired End State

[A specification of the desired end state after this plan is complete, and how to verify it]

### Key Discoveries:
- [Important finding with file:line reference]
- [Pattern to follow]
- [Constraint to work within]

## What We're NOT Doing

[Explicitly list out-of-scope items to prevent scope creep]

## Implementation Approach

[High-level strategy and reasoning]

---

<details open>
<summary><h2>Phase 1: [Descriptive Name]</h2></summary>

### Overview
[What this phase accomplishes]

### Changes Required:

#### 1. [Component/File Group]

<details>
<summary><code>path/to/file.ext:LINE_NUMBER</code></summary>

```diff
 // Context line (unchanged)
-// Line being removed or modified
+// New or modified line
```

</details>

### Success Criteria:

#### Automated Verification:
- [ ] Tests pass: `pytest tests/`
- [ ] Type checking passes: `mypy src/`
- [ ] Linting passes: `make lint`

#### Manual Verification:
- [ ] Feature works as expected when tested
- [ ] Edge case handling verified

</details>

---

<details open>
<summary><h2>Phase 2: [Descriptive Name]</h2></summary>

[Similar structure with collapsible diff blocks...]

</details>

---

## Testing Strategy

### Unit Tests:
- [What to test]
- [Key edge cases]

### Integration Tests:
- [End-to-end scenarios]

### Manual Testing Steps:
1. [Specific step to verify feature]
2. [Another verification step]
3. [Edge case to test manually]

## Performance Considerations

[Any performance implications or optimizations needed]

## Migration Notes

[If applicable, how to handle existing data/systems]
<!-- /kiln:plan -->
````

## Important Guidelines

1. **Be Autonomous**:
   - Make decisions without asking
   - Use codebase patterns as guidance
   - If something is unclear, make a reasonable decision and note the assumption

2. **Be Thorough**:
   - Read all context files COMPLETELY before planning
   - Research actual code patterns using parallel sub-tasks
   - Include specific file paths and line numbers
   - Write measurable success criteria with clear automated vs manual distinction

3. **Be Practical**:
   - Focus on incremental, testable changes
   - Consider migration and rollback
   - Think about edge cases
   - Include "what we're NOT doing"

4. **Be Concise with Code**:
   - Show only diffs, NOT full file contents
   - Use `diff` syntax with +/- to show additions/removals
   - Include just enough context lines to locate the change
   - For new methods/functions, show only the new code (not surrounding file)
   - For tests, list test names rather than full implementations
   - Wrap each diff block in `<details>` tags with the file path as summary

5. **Use Collapsible Sections**:
   - Wrap each phase in `<details open>` tags (expanded by default, but collapsible)
   - Wrap diff blocks in `<details>` tags (collapsed by default)
   - When writing plan, collapse the research section in `<details>` tags
   - Always include blank line after `<summary>` and before `</details>` for GitHub markdown rendering

6. **Track Progress**:
   - Use TodoWrite to track planning tasks
   - Update todos as you complete research

7. **No Open Questions in Final Plan**:
   - If you encounter open questions during planning, research more
   - Do NOT write the plan with unresolved questions
   - The implementation plan must be complete and actionable
   - Every decision must be made before finalizing the plan
   - Note assumptions where you made autonomous decisions

## Success Criteria Guidelines

**Always separate success criteria into two categories:**

1. **Automated Verification** (can be run by execution agents):
   - Commands that can be run: `pytest`, `mypy`, `make lint`, etc.
   - Specific files that should exist
   - Code compilation/type checking
   - Automated test suites

2. **Manual Verification** (requires human testing):
   - UI/UX functionality
   - Performance under real conditions
   - Edge cases that are hard to automate
   - User acceptance criteria

**Format example:**
```markdown
### Success Criteria:

#### Automated Verification:
- [ ] All unit tests pass: `pytest tests/`
- [ ] No type errors: `mypy src/`
- [ ] No linting errors: `make lint`

#### Manual Verification:
- [ ] New feature appears correctly in logs
- [ ] Performance is acceptable under load
- [ ] Error messages are clear
```

## Common Patterns

### For Database Changes:
- Start with schema/migration
- Add store methods
- Update business logic
- Expose via API

### For New Features:
- Research existing patterns first
- Start with data model
- Build backend logic
- Add API endpoints
- Implement UI last

### For Refactoring:
- Document current behavior
- Plan incremental changes
- Maintain backwards compatibility
- Include migration strategy

## Sub-task Spawning Best Practices

When spawning research sub-tasks:

1. **Spawn multiple tasks in parallel** for efficiency
2. **Each task should be focused** on a specific area
3. **Be specific about what to search for**
4. **Request specific file:line references** in responses
5. **Wait for all tasks to complete** before synthesizing
6. **Verify sub-task results**:
   - If a sub-task returns unexpected results, spawn follow-up tasks
   - Cross-check findings against the actual codebase

## Output

When done, output a brief summary:
```
Done - Plan posted to issue #X.
```
