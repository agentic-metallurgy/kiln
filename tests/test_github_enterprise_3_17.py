"""Unit tests for the GitHub Enterprise Server 3.17 client module."""

import pytest

from src.ticket_clients import (
    GitHubEnterprise317Client,
    get_github_client,
)


@pytest.fixture
def ghes_317_client():
    """Fixture providing a GitHubEnterprise317Client instance."""
    return GitHubEnterprise317Client(tokens={"enterprise.example.com": "test-token"})


@pytest.mark.unit
class TestGitHubEnterprise317Client:
    """Tests for GitHubEnterprise317Client specific behavior."""

    def test_supports_sub_issues_returns_false(self, ghes_317_client):
        """Test that supports_sub_issues returns False for GHES 3.17."""
        assert ghes_317_client.supports_sub_issues is False

    def test_client_description(self, ghes_317_client):
        """Test that client_description returns the correct string."""
        assert ghes_317_client.client_description == "GitHub Enterprise Server 3.17"

    def test_get_parent_issue_returns_none(self, ghes_317_client):
        """Test that get_parent_issue returns None since sub-issues are not supported."""
        result = ghes_317_client.get_parent_issue("enterprise.example.com/owner/repo", 123)
        assert result is None

    def test_get_child_issues_returns_empty_list(self, ghes_317_client):
        """Test that get_child_issues returns empty list since sub-issues are not supported."""
        result = ghes_317_client.get_child_issues("enterprise.example.com/owner/repo", 123)
        assert result == []

    def test_factory_returns_317_client(self):
        """Test that get_github_client returns GitHubEnterprise317Client for version 3.17."""
        client = get_github_client(enterprise_version="3.17")
        assert isinstance(client, GitHubEnterprise317Client)
        assert client.client_description == "GitHub Enterprise Server 3.17"

    def test_factory_returns_317_client_with_whitespace(self):
        """Test that get_github_client handles whitespace in version string."""
        client = get_github_client(enterprise_version=" 3.17 ")
        assert isinstance(client, GitHubEnterprise317Client)
