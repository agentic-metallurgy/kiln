"""GitHub Enterprise Server 3.19 implementation of the TicketClient protocol.

GHES 3.19 has API parity with github.com for the features Kiln uses:
- closedByPullRequestsReferences is available
- Project V2 timeline events (ADDED_TO_PROJECT_V2_EVENT, PROJECT_V2_ITEM_STATUS_CHANGED_EVENT)
- Sub-issues API is available

This client extends GitHubTicketClient with GHES-specific CLI handling.
"""

from src.logger import get_logger
from src.ticket_clients.github import GitHubTicketClient

logger = get_logger(__name__)


class GitHubEnterprise319Client(GitHubTicketClient):
    """GitHub Enterprise Server 3.19 implementation of TicketClient protocol.

    GHES 3.19 has full API compatibility with github.com for Kiln's needs.
    This client inherits all functionality from GitHubTicketClient.
    """

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.19"
