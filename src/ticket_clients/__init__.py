"""GitHub ticket client implementations.

This package provides GitHub client implementations for different GitHub versions:
- GitHubTicketClient: For github.com (full feature support)
- GitHubEnterprise314Client: For GHES 3.14 (limited features)
- GitHubEnterprise315Client: For GHES 3.15 (same limitations as 3.14)
- GitHubEnterprise316Client: For GHES 3.16 (same limitations as 3.14)
- GitHubEnterprise317Client: For GHES 3.17 (same limitations as 3.14)
- GitHubEnterprise318Client: For GHES 3.18 (sub-issues support added)
- GitHubEnterprise319Client: For GHES 3.19 (full feature support)

Use get_github_client() factory function to get the appropriate client based
on the GITHUB_ENTERPRISE_VERSION configuration.
"""

from src.ticket_clients.base import GitHubClientBase, NetworkError
from src.ticket_clients.github import GitHubTicketClient
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client
from src.ticket_clients.github_enterprise_3_15 import GitHubEnterprise315Client
from src.ticket_clients.github_enterprise_3_16 import GitHubEnterprise316Client
from src.ticket_clients.github_enterprise_3_17 import GitHubEnterprise317Client
from src.ticket_clients.github_enterprise_3_18 import GitHubEnterprise318Client
from src.ticket_clients.github_enterprise_3_19 import GitHubEnterprise319Client

# Type alias for all GitHub client types
# Some GHES versions extend GitHubClientBase (limited features)
# while others extend GitHubTicketClient (full features like 3.17, 3.19)
GitHubClient = GitHubClientBase | GitHubTicketClient

# Mapping of GHES versions to their client classes
GHES_VERSION_CLIENTS: dict[str, type[GitHubClient]] = {
    "3.14": GitHubEnterprise314Client,
    "3.15": GitHubEnterprise315Client,
    "3.16": GitHubEnterprise316Client,
    "3.17": GitHubEnterprise317Client,
    "3.18": GitHubEnterprise318Client,
    "3.19": GitHubEnterprise319Client,
}


def get_github_client(
    tokens: dict[str, str] | None = None,
    enterprise_version: str | None = None,
) -> GitHubClient:
    """Factory function to get the appropriate GitHub client.

    Args:
        tokens: Dictionary mapping hostname to token
        enterprise_version: GHES version string (e.g., "3.14") or None for github.com

    Returns:
        Appropriate GitHub client instance

    Raises:
        ValueError: If the specified GHES version is not supported
    """
    if enterprise_version is None:
        # github.com - use the standard client
        return GitHubTicketClient(tokens)

    # Normalize version string
    version = enterprise_version.strip()

    if version not in GHES_VERSION_CLIENTS:
        supported = ", ".join(sorted(GHES_VERSION_CLIENTS.keys()))
        raise ValueError(
            f"Unsupported GitHub Enterprise Server version: {version}. "
            f"Supported versions: {supported}"
        )

    client_class = GHES_VERSION_CLIENTS[version]
    return client_class(tokens)


__all__ = [
    "GitHubClientBase",
    "GitHubTicketClient",
    "GitHubEnterprise314Client",
    "GitHubEnterprise315Client",
    "GitHubEnterprise316Client",
    "GitHubEnterprise317Client",
    "GitHubEnterprise318Client",
    "GitHubEnterprise319Client",
    "NetworkError",
    "get_github_client",
    "GHES_VERSION_CLIENTS",
]
