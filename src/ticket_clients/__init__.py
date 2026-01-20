"""GitHub ticket client implementations.

This package provides GitHub client implementations for different GitHub versions:
- GitHubTicketClient: For github.com (full feature support)
- GitHubEnterprise314Client: For GHES 3.14 (limited features)

Use get_github_client() factory function to get the appropriate client based
on the GITHUB_ENTERPRISE_VERSION configuration.
"""

from src.ticket_clients.base import GitHubClientBase
from src.ticket_clients.github import GitHubTicketClient
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client
from src.ticket_clients.github_enterprise_3_19 import GitHubEnterprise319Client

# Mapping of GHES versions to their client classes
GHES_VERSION_CLIENTS: dict[str, type[GitHubClientBase]] = {
    "3.14": GitHubEnterprise314Client,
    "3.19": GitHubEnterprise319Client,
}


def get_github_client(
    tokens: dict[str, str] | None = None,
    enterprise_version: str | None = None,
) -> GitHubClientBase:
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
    "GitHubEnterprise319Client",
    "get_github_client",
    "GHES_VERSION_CLIENTS",
]
