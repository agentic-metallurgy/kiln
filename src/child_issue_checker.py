"""Child issue status checker for parent PRs.

This module provides functionality to manage commit status checks on parent PRs
based on whether their child issues have been resolved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.logger import get_logger

if TYPE_CHECKING:
    from src.ticket_clients.github import GitHubTicketClient

logger = get_logger(__name__)

# Context name for the commit status check
CHILD_ISSUES_CHECK_CONTEXT = "kiln/child-issues-check"


def update_parent_pr_status(
    client: GitHubTicketClient,
    repo: str,
    parent_issue: int,
) -> None:
    """Update the commit status on a parent issue's PR based on child issue states.

    Sets a commit status check on the parent's PR to block merging while
    child issues are still open. When all children are closed/merged,
    the status is set to success to allow the parent PR to merge.

    Args:
        client: GitHubTicketClient instance
        repo: Repository in 'hostname/owner/repo' format
        parent_issue: Parent issue number
    """
    # Get parent's open PR
    parent_pr = client.get_pr_for_issue(repo, parent_issue)
    if not parent_pr:
        logger.debug(f"No open PR found for parent issue #{parent_issue}")
        return

    # Get children
    children = client.get_child_issues(repo, parent_issue)
    open_children = [c for c in children if c["state"] == "open"]

    # Get PR head SHA
    sha = client.get_pr_head_sha(repo, parent_pr["number"])
    if not sha:
        logger.warning(f"Could not get HEAD SHA for PR #{parent_pr['number']}")
        return

    # Set status based on open children
    if open_children:
        client.set_commit_status(
            repo=repo,
            sha=sha,
            state="failure",
            context=CHILD_ISSUES_CHECK_CONTEXT,
            description=f"{len(open_children)} child issue(s) still open",
        )
        logger.info(
            f"Set {CHILD_ISSUES_CHECK_CONTEXT}=failure on PR #{parent_pr['number']} "
            f"({len(open_children)} open children)"
        )
    else:
        client.set_commit_status(
            repo=repo,
            sha=sha,
            state="success",
            context=CHILD_ISSUES_CHECK_CONTEXT,
            description="All child issues resolved",
        )
        logger.info(
            f"Set {CHILD_ISSUES_CHECK_CONTEXT}=success on PR #{parent_pr['number']} "
            "(all children resolved)"
        )
