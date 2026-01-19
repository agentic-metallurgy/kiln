---
name: edit-github-issue-components
description: Edit GitHub issue components (description, research, implementation plan) in-place. Use when updating existing issue content rather than adding new comments.
---

# Editing GitHub Issue Components In-Place

When working with GitHub issues, content is organized into distinct components. **Always edit these in-place** rather than appending new comments or duplicating content.

## Issue Components

| Component | Location | How to Edit |
|-----------|----------|-------------|
| **Description** | Issue body (before any kiln sections) | `gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."` |
| **Research** | Section in description between `<!-- kiln:research -->` and `<!-- /kiln:research -->` | `gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."` |
| **Implementation Plan** | Section in description between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->` | `gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."` |

**Note**: The repository is provided in `hostname/owner/repo` format. Use the full URL format for all gh CLI commands.

## CRITICAL Rules

1. **NEVER** add comments for research or plans — they go in the issue description
2. **NEVER** create duplicate sections — find and edit the existing section
3. **ALWAYS** preserve the original description and other sections when editing
4. **ALWAYS** use the HTML comment markers to wrap kiln sections

## How to Edit Each Component

### Editing the Issue Description (with sections)

All kiln content lives in the issue description. The structure is:

```markdown
[Original issue description]

---
<!-- kiln:research -->
## Research Findings
[Research content]
<!-- /kiln:research -->

---
<!-- kiln:plan -->
# Implementation Plan
[Plan content]
<!-- /kiln:plan -->
```

### Editing a Specific Section

1. **Fetch the current description**:
```bash
gh issue view https://<hostname>/<owner>/<repo>/issues/<num> --json body --jq '.body'
```

2. **Parse and modify the relevant section** while preserving the rest

3. **Update the description**:
```bash
gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "$(cat <<'EOF'
[Full updated description with all sections]
EOF
)"
```

### Adding a New Section (Only If It Doesn't Exist)

If a section doesn't exist yet, append it to the description:

```bash
# Get current body and append new section
CURRENT_BODY=$(gh issue view https://<hostname>/<owner>/<repo>/issues/<num> --json body --jq '.body')
NEW_BODY="$CURRENT_BODY

---
<!-- kiln:research -->
## Research Findings

[Research content here]
<!-- /kiln:research -->"

gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "$NEW_BODY"
```

## Quick Reference

| Task | Command |
|------|---------|
| View description | `gh issue view https://<hostname>/<owner>/<repo>/issues/<num> --json body --jq '.body'` |
| Edit description | `gh issue edit https://<hostname>/<owner>/<repo>/issues/<num> --body "..."` |
| Check if section exists | Look for `<!-- kiln:research -->` or `<!-- kiln:plan -->` in body |

## Anti-Patterns to Avoid

- Adding research/plan as comments — NO, they go in the description
- Creating "## Implementation Plan v2" — NO, edit the existing section
- Adding comments to communicate updates — NO, edit sections in-place
- Forgetting the HTML markers — NO, always wrap sections with markers
