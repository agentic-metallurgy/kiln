"""Shared fixtures for GitHub client tests."""

import pytest

from src.ticket_clients.github import GitHubTicketClient
from src.ticket_clients.github_enterprise_3_18 import GitHubEnterprise318Client


@pytest.fixture
def github_client():
    """Fixture providing a GitHubTicketClient instance."""
    return GitHubTicketClient(tokens={"github.com": "test-token"})


@pytest.fixture
def enterprise_318_client():
    """Fixture providing a GitHubEnterprise318Client instance."""
    return GitHubEnterprise318Client(tokens={"github.mycompany.com": "test-token"})
