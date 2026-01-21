"""GitHub Enterprise Server 3.15 implementation of the TicketClient protocol.

GHES 3.15 uses REST API version 2022-11-28, identical to GHES 3.14, and has the
same API limitations for features Kiln uses:
- closedByPullRequestsReferences is NOT available (uses CLOSED_EVENT instead)
- sub-issues API is NOT available
- Project V2 timeline events don't exist (uses field creator instead)

This client inherits all functionality from GitHubEnterprise314Client,
only overriding the client description for logging/debugging purposes.
"""

from src.logger import get_logger
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client

logger = get_logger(__name__)


class GitHubEnterprise315Client(GitHubEnterprise314Client):
    """GitHub Enterprise Server 3.15 implementation of TicketClient protocol.

    GHES 3.15 has identical API limitations to GHES 3.14 (both use REST API
    version 2022-11-28). This client inherits all workarounds and functionality
    from GitHubEnterprise314Client.
    """

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.15"
