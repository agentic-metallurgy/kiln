"""Implementation workflow for executing the implementation plan."""

from src.logger import get_logger
from src.workflows.base import WorkflowContext

logger = get_logger(__name__)


class ImplementWorkflow:
    """Workflow for implementing the planned changes.

    This workflow guides Claude through executing the implementation plan,
    creating a draft PR, and iterating with the pr-review agent until approved.
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "implement"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate implementation prompts for the given issue.

        Args:
            ctx: WorkflowContext with issue and repository information

        Returns:
            list[str]: Ordered list of implementation prompts
        """
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        # Build reviewer flags for PR creation
        reviewer_flags = ""
        if ctx.allowed_username:
            reviewer_flags = f" --reviewer {ctx.allowed_username}"

        project_url_context = ""
        if ctx.project_url:
            project_url_context = f" Project URL: {ctx.project_url}"

        prompts = [
            f"/implement_github for issue {issue_url}.{reviewer_flags}{project_url_context}",
        ]

        logger.debug(f"Implement workflow prompt: {prompts[0]}")

        return prompts
