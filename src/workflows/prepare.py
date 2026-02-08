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

    def _get_repo_identifier(self, repo: str) -> str:
        """Get a unique, filesystem-safe identifier for a repository.

        Converts 'hostname/owner/repo' or 'owner/repo' to 'owner_repo'.
        This ensures repos with the same name but different owners have unique paths.

        Args:
            repo: Repository in 'hostname/owner/repo' or 'owner/repo' format

        Returns:
            Filesystem-safe identifier like 'owner_repo'
        """
        parts = repo.split("/")
        if len(parts) >= 2:
            # Take last two segments: owner and repo
            return f"{parts[-2]}_{parts[-1]}"
        # Fallback for unexpected format
        return parts[-1]

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
        # Use unique repo identifier (owner_repo) to avoid path collisions
        repo_id = self._get_repo_identifier(ctx.repo)
        # Use absolute paths so Claude knows exactly where to create things
        workspace = ctx.workspace_path  # This is now an absolute path
        repo_path = f"{workspace}/{repo_id}"
        worktree_path = f"{workspace}/{repo_id}-issue-{ctx.issue_number}"
        clone_url = self._get_clone_url(ctx)

        # Determine base branch for worktree
        if ctx.parent_branch:
            if ctx.parent_issue_number:
                # Implicit: parent branch from parent issue's PR
                base_branch_instruction = (
                    f"Create the worktree from the parent branch '{ctx.parent_branch}' "
                    f"(this is the branch from the parent issue #{ctx.parent_issue_number}'s open PR). "
                    f"First fetch the parent branch from origin: `git fetch origin {ctx.parent_branch}`, "
                    f"then create the worktree from it."
                )
            else:
                # Explicit: feature_branch from issue frontmatter
                base_branch_instruction = (
                    f"Create the worktree from the feature branch '{ctx.parent_branch}' "
                    f"(specified in issue frontmatter). "
                    f"First fetch the branch from origin: `git fetch origin {ctx.parent_branch}`, "
                    f"then create the worktree from it."
                )
        else:
            base_branch_instruction = "Create the worktree from the main branch."

        return [
            f"Clone {clone_url} to {repo_path} if missing. If it exists, pull from origin main to sync it to the latest commit.",
            (
                f"Create a git worktree at exactly this path: {worktree_path}\n"
                f"{base_branch_instruction} "
                f"The folder MUST be created at the exact path specified above - do not create it anywhere else. "
                f"The branch name MUST start with the issue number ({ctx.issue_number}-) followed by a semantic slug based on the issue's details:\n"
                f"Issue title: {ctx.issue_title}\n\n"
                f"Issue description:\n{ctx.issue_body}"
            ),
        ]
