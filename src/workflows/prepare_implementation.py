"""Workflow for preparing implementation by creating draft PR with task list."""

from src.logger import get_logger
from src.workflows.base import WorkflowContext

logger = get_logger(__name__)


class PrepareImplementationWorkflow:
    """Workflow for creating a draft PR with the task list from the plan.

    This workflow:
    1. Creates an empty commit to establish a PR
    2. Creates a draft PR with the plan's task list as checkboxes
    3. Prepares the ground for iterative implementation
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "prepare_implementation"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate prepare implementation prompts.

        Args:
            ctx: WorkflowContext with issue and repository information

        Returns:
            list[str]: Ordered list of prompts
        """
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        prompts = [
            f"/prepare_implementation_github for issue {issue_url}.",
        ]

        logger.debug(f"PrepareImplementation workflow prompt: {prompts[0]}")

        return prompts
