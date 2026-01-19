"""Prepare workflow for setting up the workspace before other workflows."""

from src.workflows.base import WorkflowContext


def parse_repo(repo: str) -> tuple[str, str]:
    """Parse hostname/owner/repo format into (hostname, owner/repo).

    Args:
        repo: Repository in format "hostname/owner/repo"

    Returns:
        Tuple of (hostname, owner/repo)
    """
    parts = repo.split("/", 1)
    if len(parts) == 2 and "." in parts[0]:
        return parts[0], parts[1]
    # Fallback for old format (shouldn't happen)
    return "github.com", repo


class PrepareWorkflow:
    """Workflow for preparing the workspace.

    This workflow runs before research to ensure the main repo
    is cloned or updated in the workspace.
    """

    @property
    def name(self) -> str:
        """Return workflow name."""
        return "prepare"

    def _get_clone_url(self, ctx: WorkflowContext) -> str:
        """Get the git clone URL for the repository.

        Parses hostname from ctx.repo (format: hostname/owner/repo).
        """
        hostname, owner_repo = parse_repo(ctx.repo)
        return f"https://{hostname}/{owner_repo}.git"

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Generate prepare prompts for the given issue.

        Args:
            ctx: WorkflowContext with issue and repository information.

        Returns:
            list[str]: Ordered list of prepare prompts
        """
        # Extract repo name from 'hostname/owner/repo' format (last segment)
        repo_name = ctx.repo.split("/")[-1] if "/" in ctx.repo else ctx.repo
        # Use simple names without workspace prefix since Claude's cwd is already the workspace
        worktree_name = f"{repo_name}-issue-{ctx.issue_number}"
        clone_url = self._get_clone_url(ctx)

        # Determine base branch for worktree
        if ctx.parent_branch:
            base_branch_instruction = (
                f"Create the worktree from the parent branch '{ctx.parent_branch}' "
                f"(this is the branch from the parent issue #{ctx.parent_issue_number}'s open PR). "
                f"First fetch the parent branch from origin: `git fetch origin {ctx.parent_branch}`, "
                f"then create the worktree from it."
            )
        else:
            base_branch_instruction = "Create the worktree from the main branch."

        return [
            f"Clone {clone_url} to {repo_name} if missing. If it exists, pull from origin main to sync it to the latest commit.",
            (
                f"Create a worktree at {worktree_name} for issue #{ctx.issue_number}. "
                f"{base_branch_instruction} "
                f"The folder name must always match the provided path exactly. "
                f"The branch name MUST start with the issue number ({ctx.issue_number}-) followed by a semantic slug based on the issue's details:\n"
                f"Issue title: {ctx.issue_title}\n\n"
                f"Issue description:\n{ctx.issue_body}"
            ),
        ]
