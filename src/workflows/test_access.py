"""Test access workflow for verifying GitHub access works."""

from src.workflows.base import WorkflowContext


class TestAccessWorkflow:
    """Workflow for testing GitHub access.

    Simple workflow that views an issue and edits it to prove access works.
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "test_access"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate test access prompt for the given issue.

        Args:
            ctx: WorkflowContext with issue and repository information

        Returns:
            list[str]: Single prompt to test access
        """
        # ctx.repo is hostname/owner/repo format
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        prompts = [
            f"/view-edit-github-issue {issue_url}",
        ]

        return prompts
