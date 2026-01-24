"""Unit tests for GitHub Enterprise client functionality."""

from unittest.mock import patch

import pytest

from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client
from src.ticket_clients.github_enterprise_3_18 import GitHubEnterprise318Client


@pytest.mark.unit
class TestGitHubEnterprise318Client:
    """Tests for GitHubEnterprise318Client behavior and capabilities."""

    def test_supports_sub_issues_returns_true(self, enterprise_318_client):
        """Test that supports_sub_issues property returns True for GHES 3.18."""
        assert enterprise_318_client.supports_sub_issues is True

    def test_supports_linked_prs_returns_true(self, enterprise_318_client):
        """Test that supports_linked_prs property returns True (inherited from 3.14)."""
        assert enterprise_318_client.supports_linked_prs is True

    def test_supports_status_actor_check_returns_true(self, enterprise_318_client):
        """Test that supports_status_actor_check property returns True (inherited from 3.14)."""
        assert enterprise_318_client.supports_status_actor_check is True

    def test_client_description_returns_correct_string(self, enterprise_318_client):
        """Test that client_description returns 'GitHub Enterprise Server 3.18'."""
        assert enterprise_318_client.client_description == "GitHub Enterprise Server 3.18"

    def test_inherits_from_enterprise_314_client(self, enterprise_318_client):
        """Test that GitHubEnterprise318Client inherits from GitHubEnterprise314Client."""
        assert isinstance(enterprise_318_client, GitHubEnterprise314Client)

    def test_get_parent_issue_with_parent(self, enterprise_318_client):
        """Test get_parent_issue returns parent issue number when present."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": {
                            "number": 42
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result == 42

    def test_get_parent_issue_without_parent(self, enterprise_318_client):
        """Test get_parent_issue returns None when issue has no parent."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": None
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result is None

    def test_get_parent_issue_nonexistent_issue(self, enterprise_318_client):
        """Test get_parent_issue returns None for nonexistent issue."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 99999
            )

        assert result is None

    def test_get_parent_issue_uses_sub_issues_header(self, enterprise_318_client):
        """Test get_parent_issue uses the GraphQL-Features: sub_issues header."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "parent": None
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            enterprise_318_client.get_parent_issue("github.mycompany.com/owner/repo", 123)

            call_args = mock_query.call_args
            # Check positional or keyword args for headers
            if len(call_args[0]) >= 3:
                headers = call_args[0][2]
            else:
                headers = call_args[1].get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers

    def test_get_parent_issue_handles_api_error(self, enterprise_318_client):
        """Test get_parent_issue returns None on API error."""
        with patch.object(
            enterprise_318_client,
            "_execute_graphql_query_with_headers",
            side_effect=Exception("API error"),
        ):
            result = enterprise_318_client.get_parent_issue(
                "github.mycompany.com/owner/repo", 123
            )

        assert result is None

    def test_get_child_issues_with_children(self, enterprise_318_client):
        """Test get_child_issues returns list of child issues."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 101, "state": "OPEN"},
                                {"number": 102, "state": "CLOSED"},
                                {"number": 103, "state": "OPEN"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert len(result) == 3
        assert result[0] == {"number": 101, "state": "OPEN"}
        assert result[1] == {"number": 102, "state": "CLOSED"}
        assert result[2] == {"number": 103, "state": "OPEN"}

    def test_get_child_issues_without_children(self, enterprise_318_client):
        """Test get_child_issues returns empty list when no children."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert result == []

    def test_get_child_issues_nonexistent_issue(self, enterprise_318_client):
        """Test get_child_issues returns empty list for nonexistent issue."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 99999
            )

        assert result == []

    def test_get_child_issues_uses_sub_issues_header(self, enterprise_318_client):
        """Test get_child_issues uses the GraphQL-Features: sub_issues header."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            enterprise_318_client.get_child_issues("github.mycompany.com/owner/repo", 42)

            call_args = mock_query.call_args
            # Check positional or keyword args for headers
            if len(call_args[0]) >= 3:
                headers = call_args[0][2]
            else:
                headers = call_args[1].get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers

    def test_get_child_issues_handles_api_error(self, enterprise_318_client):
        """Test get_child_issues returns empty list on API error."""
        with patch.object(
            enterprise_318_client,
            "_execute_graphql_query_with_headers",
            side_effect=Exception("API error"),
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert result == []

    def test_get_child_issues_handles_null_nodes(self, enterprise_318_client):
        """Test get_child_issues handles null entries in nodes array."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 101, "state": "OPEN"},
                                None,  # Can occur with deleted issues
                                {"number": 103, "state": "OPEN"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            enterprise_318_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            result = enterprise_318_client.get_child_issues(
                "github.mycompany.com/owner/repo", 42
            )

        assert len(result) == 2
        assert result[0] == {"number": 101, "state": "OPEN"}
        assert result[1] == {"number": 103, "state": "OPEN"}


@pytest.mark.unit
class TestGHES318VersionRegistry:
    """Tests for GHES 3.18 version in the client registry."""

    def test_get_github_client_returns_318_client(self):
        """Test that get_github_client returns GitHubEnterprise318Client for version 3.18."""
        from src.ticket_clients import get_github_client

        client = get_github_client(enterprise_version="3.18")

        assert isinstance(client, GitHubEnterprise318Client)
        assert client.client_description == "GitHub Enterprise Server 3.18"

    def test_version_registry_contains_318(self):
        """Test that GHES_VERSION_CLIENTS dict contains 3.18."""
        from src.ticket_clients import GHES_VERSION_CLIENTS

        assert "3.18" in GHES_VERSION_CLIENTS
        assert GHES_VERSION_CLIENTS["3.18"] is GitHubEnterprise318Client


@pytest.mark.unit
class TestGHES316Client:
    """Tests for GitHubEnterprise316Client."""

    def test_get_github_client_returns_ghes_316_client(self):
        """Test that get_github_client returns GitHubEnterprise316Client for version 3.16."""
        from src.ticket_clients import GitHubEnterprise316Client, get_github_client

        client = get_github_client(enterprise_version="3.16")
        assert isinstance(client, GitHubEnterprise316Client)

    def test_client_description_returns_expected_value(self):
        """Test that client_description returns 'GitHub Enterprise Server 3.16'."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.client_description == "GitHub Enterprise Server 3.16"

    def test_ghes_316_inherits_from_ghes_314(self):
        """Test that GitHubEnterprise316Client inherits from GitHubEnterprise314Client."""
        from src.ticket_clients import GitHubEnterprise314Client, GitHubEnterprise316Client

        assert issubclass(GitHubEnterprise316Client, GitHubEnterprise314Client)

    def test_supports_linked_prs_property(self):
        """Test that supports_linked_prs returns True (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_linked_prs is True

    def test_supports_sub_issues_property(self):
        """Test that supports_sub_issues returns False (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_sub_issues is False

    def test_supports_status_actor_check_property(self):
        """Test that supports_status_actor_check returns True (inherited from GHES 3.14)."""
        from src.ticket_clients import GitHubEnterprise316Client

        client = GitHubEnterprise316Client()
        assert client.supports_status_actor_check is True
