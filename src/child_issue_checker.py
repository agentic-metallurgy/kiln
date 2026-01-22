"""Child issue checker for updating parent PR status.

This module provides functionality to check child issue states and update
the parent PR's commit status accordingly. When all child issues are closed,
the parent PR can be merged.
"""

from src.logger import get_logger
from src.ticket_clients.github import GitHubTicketClient

logger = get_logger(__name__)

# Commit status context used for child issue checks
CHILD_ISSUES_CONTEXT = "kiln/child-issues"


def update_parent_pr_status(
    ticket_client: GitHubTicketClient,
    repo: str,
    parent_issue_number: int,
) -> bool:
    """Update the parent PR's commit status based on child issue states.

    Checks all child issues of the parent and sets the parent PR's commit
    status to:
    - 'pending' if any child issues are still open
    - 'success' if all child issues are closed

    Args:
        ticket_client: GitHubTicketClient instance
        repo: Repository in 'hostname/owner/repo' format
        parent_issue_number: The parent issue number

    Returns:
        True if status was updated successfully, False otherwise
    """
    # Get the parent's open PR
    parent_pr = ticket_client.get_pr_for_issue(repo, parent_issue_number)
    if parent_pr is None:
        logger.debug(f"Parent issue #{parent_issue_number} has no open PR")
        return False

    pr_number = parent_pr.get("number")
    if not pr_number:
        logger.warning(f"Could not get PR number for parent issue #{parent_issue_number}")
        return False

    # Get the PR's HEAD SHA
    head_sha = ticket_client.get_pr_head_sha(repo, int(pr_number))
    if not head_sha:
        logger.warning(f"Could not get HEAD SHA for PR #{pr_number}")
        return False

    # Get child issues
    children = ticket_client.get_child_issues(repo, parent_issue_number)
    if not children:
        # No children - set status to success
        logger.info(f"Parent issue #{parent_issue_number} has no child issues")
        return ticket_client.set_commit_status(
            repo=repo,
            sha=head_sha,
            state="success",
            context=CHILD_ISSUES_CONTEXT,
            description="No child issues",
        )

    # Check for open children
    open_children = [c for c in children if c.get("state") == "OPEN"]
    total_children = len(children)
    open_count = len(open_children)

    if open_count > 0:
        # Some children still open
        description = f"{open_count} of {total_children} child issue(s) still open"
        state = "pending"
    else:
        # All children closed
        description = f"All {total_children} child issue(s) resolved"
        state = "success"

    logger.info(f"Updating parent PR #{pr_number} status: {state} - {description}")

    return ticket_client.set_commit_status(
        repo=repo,
        sha=head_sha,
        state=state,
        context=CHILD_ISSUES_CONTEXT,
        description=description,
    )
