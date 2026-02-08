"""Unit tests for the GitHub Enterprise Server 3.15 client module."""

import pytest

from src.ticket_clients import get_github_client
from src.ticket_clients.github_enterprise_3_15 import GitHubEnterprise315Client


@pytest.mark.unit
class TestGitHubEnterprise315Client:
    """Tests for GitHubEnterprise315Client."""

    @pytest.fixture
    def client(self):
        """Fixture providing a GitHubEnterprise315Client instance."""
        return GitHubEnterprise315Client(tokens={"github.example.com": "test-token"})

    def test_client_description(self, client):
        """Test client_description returns correct value."""
        assert client.client_description == "GitHub Enterprise Server 3.15"

    def test_supports_linked_prs(self, client):
        """Test supports_linked_prs returns True (via workaround)."""
        assert client.supports_linked_prs is True

    def test_supports_sub_issues(self, client):
        """Test supports_sub_issues returns False (not available)."""
        assert client.supports_sub_issues is False

    def test_supports_status_actor_check(self, client):
        """Test supports_status_actor_check returns True (via workaround)."""
        assert client.supports_status_actor_check is True


@pytest.mark.unit
class TestGetGitHubClientFactory315:
    """Tests for get_github_client factory with 3.15 version."""

    def test_factory_returns_315_client(self):
        """Test factory returns GitHubEnterprise315Client for version 3.15."""
        client = get_github_client(enterprise_version="3.15")
        assert isinstance(client, GitHubEnterprise315Client)

    def test_factory_with_whitespace(self):
        """Test factory handles version with whitespace."""
        client = get_github_client(enterprise_version=" 3.15 ")
        assert isinstance(client, GitHubEnterprise315Client)
