"""GitHub Enterprise Server 3.16 implementation of the TicketClient protocol.

GHES 3.16 has the same API limitations as GHES 3.14:
- closedByPullRequestsReferences is NOT available
- sub-issues API is NOT available
- Project V2 timeline events don't exist

This client extends GitHubEnterprise314Client to reuse all workarounds.
"""

from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client


class GitHubEnterprise316Client(GitHubEnterprise314Client):
    """GitHub Enterprise Server 3.16 implementation of TicketClient protocol.

    GHES 3.16 has identical API limitations to GHES 3.14.
    This client inherits all workaround functionality from GitHubEnterprise314Client.
    """

    @property
    def client_description(self) -> str:
        """Human-readable description of this client."""
        return "GitHub Enterprise Server 3.16"
