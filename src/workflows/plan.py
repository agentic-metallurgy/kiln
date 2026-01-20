"""Planning workflow for creating implementation plans from research findings."""

from src.logger import get_logger
from src.workflows.base import WorkflowContext

logger = get_logger(__name__)


class PlanWorkflow:
    """Workflow for creating an implementation plan.

    This workflow guides Claude through reading research findings and
    creating a detailed, actionable implementation plan.
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "plan"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate planning prompts for the given issue.

        Args:
            ctx: WorkflowContext with issue and repository information

        Returns:
            list[str]: Ordered list of planning prompts
        """
        # ctx.repo is hostname/owner/repo format
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        prompts = [
            # Prompt 1: Create implementation plan and post to GitHub issue
            f"""/kiln:create_plan_github for issue {issue_url}. Do this ONLY if the issue description doesn't already contain `<!-- kiln:plan -->`.""",
        ]

        logger.debug(f"Plan workflow prompt: {prompts[0]}")

        return prompts
