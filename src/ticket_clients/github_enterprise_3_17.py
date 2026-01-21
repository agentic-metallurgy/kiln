"""GitHub Enterprise Server 3.17 implementation of the TicketClient protocol.

GHES 3.17 has API parity with github.com for most features Kiln uses:
- closedByPullRequestsReferences is available
- Project V2 timeline events (ADDED_TO_PROJECT_V2_EVENT, PROJECT_V2_ITEM_STATUS_CHANGED_EVENT)
- Sub-issues API is NOT available

This client extends GitHubTicketClient with sub-issues disabled.
"""

from src.logger import get_logger
from src.ticket_clients.github import GitHubTicketClient

logger = get_logger(__name__)


class GitHubEnterprise317Client(GitHubTicketClient):
    """GitHub Enterprise Server 3.17 implementation of TicketClient protocol.

    GHES 3.17 has most API features from github.com except sub-issues.
    This client inherits all functionality from GitHubTicketClient and
    disables sub-issues API calls.
    """

    @property
    def supports_sub_issues(self) -> bool:
        """GHES 3.17 does NOT support sub-issues API."""
        return False

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.17"

    def get_parent_issue(self, repo: str, ticket_id: int) -> int | None:
        """Get the parent issue number if this issue is a sub-issue.

        GHES 3.17 does NOT support sub-issues API, so this always returns None.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Issue number

        Returns:
            Always None (sub-issues not supported)
        """
        logger.debug(f"Sub-issues not supported in GHES 3.17, returning None for {repo}#{ticket_id}")
        return None

    def get_child_issues(self, repo: str, ticket_id: int) -> list[dict[str, int | str]]:
        """Get child issues of a parent issue.

        GHES 3.17 does NOT support sub-issues API, so this always returns empty list.

        Args:
            repo: Repository in 'hostname/owner/repo' format
            ticket_id: Parent issue number

        Returns:
            Always empty list (sub-issues not supported)
        """
        logger.debug(f"Sub-issues not supported in GHES 3.17, returning [] for {repo}#{ticket_id}")
        return []
