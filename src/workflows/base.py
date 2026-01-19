"""Base classes and protocols for workflow definitions."""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class WorkflowContext:
    """Context information passed to workflows.

    Attributes:
        repo: Repository identifier in format "hostname/owner/repo"
              (e.g., "github.com/owner/repo" or "github.example.com/owner/repo")
        issue_number: GitHub issue number being worked on
        issue_title: Title of the GitHub issue
        workspace_path: Absolute path to the git worktree for this issue
        project_url: URL of the GitHub project (for project-level operations)
        comment_body: User comment body for comment processing workflow (optional)
        target_type: Target for comment processing: "description", "research", or "plan"
        issue_body: Pre-fetched issue body/description (optional, for PrepareWorkflow)
        allowed_username: Allowed GitHub username (optional, for reviewer assignment)
        parent_issue_number: Parent issue number if this is a child issue (optional)
        parent_branch: Branch name of parent's open PR to branch from (optional)
    """

    repo: str
    issue_number: int
    issue_title: str
    workspace_path: str
    project_url: str | None = None
    comment_body: str | None = None
    target_type: str | None = None
    issue_body: str | None = None
    allowed_username: str | None = None
    parent_issue_number: int | None = None
    parent_branch: str | None = None


class Workflow(Protocol):
    """Protocol defining the interface for all workflows.

    A workflow is a series of prompts that guide Claude through a specific
    task (e.g., research, planning, implementation). Each workflow must
    implement the name property and init method.
    """

    @property
    def name(self) -> str:
        """Return the workflow name (e.g., 'research', 'plan', 'implement').

        Returns:
            str: Unique identifier for this workflow
        """
        ...

    def init(self, ctx: WorkflowContext) -> list[str]:
        """Initialize the workflow and return a list of prompts to execute.

        Each prompt will be executed sequentially by the workflow runner.
        The prompts should reference the context (issue number, repo, etc.)
        and be detailed enough for Claude to execute independently.

        Args:
            ctx: WorkflowContext containing repo, issue info, and workspace path

        Returns:
            list[str]: Ordered list of prompts to execute
        """
        ...
