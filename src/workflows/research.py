"""Research workflow for analyzing GitHub issues and exploring the codebase."""

from src.logger import get_logger
from src.workflows.base import WorkflowContext

logger = get_logger(__name__)


class ResearchWorkflow:
    """Workflow for researching a GitHub issue.

    This workflow guides Claude through understanding a GitHub issue
    and exploring the relevant parts of the codebase to gather context
    for implementation.
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "research"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate research prompts for the given issue.

        Args:
            ctx: WorkflowContext with issue and repository information

        Returns:
            list[str]: Ordered list of research prompts
        """
        # ctx.repo is hostname/owner/repo format
        issue_url = f"https://{ctx.repo}/issues/{ctx.issue_number}"

        prompts = [
            # Prompt 1: Read and understand the issue
            f"/kiln:research_codebase_github for issue {issue_url}. Edit the issue DESCRIPTION to append a research section - ONLY if the issue description doesn't already contain `<!-- kiln:research -->`. IMPORTANT: The research section MUST be wrapped in `<!-- kiln:research -->` and `<!-- /kiln:research -->` markers.",
        ]

        logger.debug(f"Research workflow prompt: {prompts[0]}")

        return prompts
