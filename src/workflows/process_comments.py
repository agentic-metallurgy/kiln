"""Workflow for processing user comments on issue components."""

from src.workflows.base import Workflow, WorkflowContext


class ProcessCommentsWorkflow(Workflow):
    """Workflow that processes user comments to edit issue components in-place."""

    @property
    def name(self) -> str:
        """Return the workflow name."""
        return "process_comments"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Initialize the workflow with prompts.

        Args:
            ctx: Workflow context with issue details

        Returns:
            List of prompts to execute
        """
        comment_body = ctx.comment_body or ""
        target_type = ctx.target_type or "description"

        # ctx.repo is hostname/owner/repo format
        # Build full issue URL that works for both github.com and GHES
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        # Map target type to human-readable description
        target_descriptions = {
            "description": "the issue description",
            "research": "the Research Findings section in the issue description (between `<!-- kiln:research -->` and `<!-- /kiln:research -->`)",
            "plan": "the Implementation Plan section in the issue description (between `<!-- kiln:plan -->` and `<!-- /kiln:plan -->`)",
        }
        target_desc = target_descriptions.get(target_type, "the issue description")

        prompts = [
            f"""Process this user comment and apply the requested changes to {target_desc}.

Issue: {issue_url}

User comment to process:
---
{comment_body}
---

Target: {target_type}

Instructions:
1. Read the current {target_type} content using: `gh issue view {issue_url} --json body`
2. Apply the user's feedback/requested changes to edit it IN-PLACE
3. Update using: `gh issue edit {issue_url} --body "..."`
4. Preserve the overall structure and formatting
5. Only modify sections relevant to the user's feedback

Do NOT create new comments. Edit the existing {target_type} directly.""",
        ]

        return prompts
