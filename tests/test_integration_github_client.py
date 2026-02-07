"""Integration tests for GitHubTicketClient.

These tests verify GitHubTicketClient functionality with mocked
external dependencies (subprocess calls to gh CLI).
"""

import json
from unittest.mock import MagicMock

import pytest

from src.ticket_clients.github import GitHubTicketClient


@pytest.mark.integration
class TestGitHubTicketClientIntegration:
    """Integration tests for GitHubTicketClient."""

    def test_parse_board_url_valid_formats(self):
        """Test _parse_board_url with various valid URL formats."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Standard org format
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/chronoboost/projects/6/views/2"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "chronoboost"
        assert num == 6

        # Without views part
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/myorg/projects/42"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert num == 42

        # With trailing slash
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/orgs/test-org/projects/123/views/1/"
        )
        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "test-org"
        assert num == 123

        # User project
        hostname, entity_type, login, num = client._parse_board_url(
            "https://github.com/users/myuser/projects/5"
        )
        assert hostname == "github.com"
        assert entity_type == "user"
        assert login == "myuser"
        assert num == 5

    def test_parse_board_url_invalid_formats(self):
        """Test _parse_board_url raises ValueError for invalid URLs."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Invalid URLs
        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("https://github.com/owner/repo")

        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("https://github.com/projects/123")

        with pytest.raises(ValueError, match="Invalid project URL format"):
            client._parse_board_url("not a url")

    def test_parse_board_item_node_valid_issue(self):
        """Test _parse_board_item_node with valid issue node data."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item123",
            "content": {
                "number": 42,
                "title": "Test Issue",
                "repository": {"nameWithOwner": "owner/repo"},
            },
            "fieldValues": {"nodes": [{"field": {"name": "Status"}, "name": "Research"}]},
        }

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")

        assert item is not None
        assert item.item_id == "PVTI_item123"
        assert item.board_url == board_url
        assert item.ticket_id == 42
        assert item.title == "Test Issue"
        assert item.repo == "github.com/owner/repo"
        assert item.status == "Research"

    def test_parse_board_item_node_non_issue(self):
        """Test _parse_board_item_node returns None for non-issue nodes."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        # Node without issue content
        node = {"id": "PVTI_item456", "content": None, "fieldValues": {"nodes": []}}

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")
        assert item is None

    def test_parse_board_item_node_missing_status(self):
        """Test _parse_board_item_node handles missing status field."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item789",
            "content": {
                "number": 99,
                "title": "No Status Issue",
                "repository": {"nameWithOwner": "owner/repo"},
            },
            "fieldValues": {"nodes": []},
        }

        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")

        assert item is not None
        assert item.status == "Unknown"

    def test_parse_board_item_node_repo_format_always_includes_hostname(self):
        """Test that repo format is always hostname/owner/repo."""
        client = GitHubTicketClient({"github.com": "fake_token"})

        node = {
            "id": "PVTI_item123",
            "content": {
                "number": 42,
                "title": "Test Issue",
                "repository": {"nameWithOwner": "myorg/myrepo"},
            },
            "fieldValues": {"nodes": []},
        }

        # Test github.com
        board_url = "https://github.com/orgs/test/projects/1"
        item = client._parse_board_item_node(node, board_url, "github.com")
        assert item.repo == "github.com/myorg/myrepo"
        # Verify format: should have exactly 2 slashes (hostname/owner/repo)
        assert item.repo.count("/") == 2
        # Verify hostname is first segment
        assert item.repo.split("/")[0] == "github.com"

    def test_execute_graphql_query_mocked(self, mock_gh_subprocess):
        """Test _execute_graphql_query with mocked subprocess."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock response
        mock_response = {"data": {"organization": {"projectV2": {"title": "Test Project"}}}}
        mock_gh_subprocess.return_value.stdout = json.dumps(mock_response)
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { organization { projectV2 { title } } }"
        variables = {"org": "testorg", "projectNumber": 1}

        result = client._execute_graphql_query(query, variables)

        assert result == mock_response
        # Verify gh was called with correct arguments
        mock_gh_subprocess.assert_called_once()
        args = mock_gh_subprocess.call_args[0][0]
        assert args[0] == "gh"
        assert "api" in args
        assert "graphql" in args

    def test_execute_graphql_query_handles_errors(self, mock_gh_subprocess):
        """Test _execute_graphql_query handles GraphQL errors in response."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock response with errors
        mock_response = {
            "errors": [{"message": "Invalid query"}, {"message": "Authentication failed"}]
        }
        mock_gh_subprocess.return_value.stdout = json.dumps(mock_response)
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { invalid }"
        variables = {}

        with pytest.raises(ValueError, match="GraphQL errors"):
            client._execute_graphql_query(query, variables)

    def test_execute_graphql_query_handles_invalid_json(self, mock_gh_subprocess):
        """Test _execute_graphql_query handles invalid JSON response."""
        client = GitHubTicketClient({"github.com": "test_token"})

        # Mock invalid JSON response
        mock_gh_subprocess.return_value.stdout = "not valid json"
        mock_gh_subprocess.return_value.returncode = 0

        query = "query { test }"
        variables = {}

        with pytest.raises(ValueError, match="Invalid JSON response"):
            client._execute_graphql_query(query, variables)


@pytest.mark.integration
class TestGitHubTicketClientLabelMethods:
    """Integration tests for GitHubTicketClient label methods."""

    def test_add_label_mocked(self, mock_gh_subprocess):
        """Test add_label uses REST API via gh issue edit."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        client.add_label("owner/repo", 42, "researching")

        # Should make single call to gh issue edit
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "--add-label" in call_args
        assert "researching" in call_args

    def test_remove_label_mocked(self, mock_gh_subprocess):
        """Test remove_label uses REST API via gh issue edit."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        client.remove_label("owner/repo", 42, "researching")

        # Should make single call to gh issue edit
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "--remove-label" in call_args
        assert "researching" in call_args

    def test_remove_label_handles_missing_label(self, mock_gh_subprocess):
        """Test remove_label handles label not on issue gracefully."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        # Simulate gh failing when label doesn't exist
        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(1, "gh")

        # Should not raise - just logs debug message
        client.remove_label("owner/repo", 42, "nonexistent-label")

        assert mock_gh_subprocess.call_count == 1


@pytest.mark.integration
class TestGitHubTicketClientIssueMethods:
    """Integration tests for GitHubTicketClient issue lifecycle methods."""

    def test_create_issue_returns_issue_number(self, mock_gh_subprocess):
        """Test create_issue parses issue number from gh CLI output."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = "https://github.com/owner/repo/issues/123\n"
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        issue_num = client.create_issue(
            "github.com/owner/repo", "Test Issue", "Test body"
        )

        assert issue_num == 123
        # Verify gh was called with correct arguments
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "create" in call_args
        assert "--title" in call_args
        assert "Test Issue" in call_args
        assert "--body" in call_args
        assert "Test body" in call_args

    def test_create_issue_handles_ghes_url(self, mock_gh_subprocess):
        """Test create_issue works with GitHub Enterprise Server URLs."""
        client = GitHubTicketClient({"github.example.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = "https://github.example.com/owner/repo/issues/456\n"
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        issue_num = client.create_issue(
            "github.example.com/owner/repo", "GHES Issue", "Body"
        )

        assert issue_num == 456

    def test_create_issue_raises_on_invalid_output(self, mock_gh_subprocess):
        """Test create_issue raises ValueError when output cannot be parsed."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = "Something went wrong\n"
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        with pytest.raises(ValueError, match="Could not parse issue number"):
            client.create_issue("github.com/owner/repo", "Test", "Body")

    def test_create_issue_propagates_subprocess_error(self, mock_gh_subprocess):
        """Test create_issue propagates CalledProcessError on gh failure."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="permission denied"
        )

        with pytest.raises(subprocess.CalledProcessError):
            client.create_issue("github.com/owner/repo", "Test", "Body")

    def test_close_issue_returns_true_on_success(self, mock_gh_subprocess):
        """Test close_issue returns True when issue is closed successfully."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        result = client.close_issue("github.com/owner/repo", 42, "not_planned")

        assert result is True
        # Verify gh was called with correct arguments
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "issue" in call_args
        assert "close" in call_args
        assert "42" in call_args
        assert "--reason" in call_args
        assert "not_planned" in call_args

    def test_close_issue_uses_completed_reason(self, mock_gh_subprocess):
        """Test close_issue uses completed reason when specified."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        result = client.close_issue("github.com/owner/repo", 99, "completed")

        assert result is True
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "completed" in call_args

    def test_close_issue_returns_false_on_failure(self, mock_gh_subprocess):
        """Test close_issue returns False when gh CLI fails."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="issue not found"
        )

        result = client.close_issue("github.com/owner/repo", 999, "not_planned")

        assert result is False

    def test_close_issue_handles_ghes_url(self, mock_gh_subprocess):
        """Test close_issue works with GitHub Enterprise Server URLs."""
        client = GitHubTicketClient({"github.example.com": "test_token"})

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        result = client.close_issue("github.example.com/owner/repo", 123, "not_planned")

        assert result is True
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "https://github.example.com/owner/repo" in " ".join(call_args)


@pytest.mark.integration
class TestGitHubTicketClientProjectMethods:
    """Integration tests for GitHubTicketClient project-related methods."""

    def test_get_issue_node_id_returns_node_id(self, mock_gh_subprocess):
        """Test get_issue_node_id returns the issue node ID on success."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "id": "I_kwDOABCDEF12345"
                    }
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        node_id = client.get_issue_node_id("github.com/owner/repo", 42)

        assert node_id == "I_kwDOABCDEF12345"
        # Verify gh was called with correct GraphQL command
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "api" in call_args
        assert "graphql" in call_args

    def test_get_issue_node_id_returns_none_for_missing_issue(self, mock_gh_subprocess):
        """Test get_issue_node_id returns None when issue doesn't exist."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        node_id = client.get_issue_node_id("github.com/owner/repo", 999)

        assert node_id is None

    def test_get_issue_node_id_returns_none_on_error(self, mock_gh_subprocess):
        """Test get_issue_node_id returns None on GraphQL error."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="network error"
        )

        node_id = client.get_issue_node_id("github.com/owner/repo", 42)

        assert node_id is None

    def test_get_issue_node_id_handles_ghes_url(self, mock_gh_subprocess):
        """Test get_issue_node_id works with GitHub Enterprise Server URLs."""
        client = GitHubTicketClient({"github.example.com": "test_token"})

        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "id": "I_kwGHES12345"
                    }
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        node_id = client.get_issue_node_id("github.example.com/owner/repo", 42)

        assert node_id == "I_kwGHES12345"

    def test_add_issue_to_project_returns_item_id(self, mock_gh_subprocess):
        """Test add_issue_to_project returns the project item ID on success."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_response = {
            "data": {
                "addProjectV2ItemById": {
                    "item": {
                        "id": "PVTI_lADOABCDEF12345"
                    }
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        item_id = client.add_issue_to_project(
            "PVT_project123", "I_kwDOABCDEF12345", "github.com"
        )

        assert item_id == "PVTI_lADOABCDEF12345"
        # Verify gh was called with correct GraphQL command
        assert mock_gh_subprocess.call_count == 1
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "api" in call_args
        assert "graphql" in call_args

    def test_add_issue_to_project_returns_none_on_failure(self, mock_gh_subprocess):
        """Test add_issue_to_project returns None when mutation fails."""
        client = GitHubTicketClient({"github.com": "test_token"})

        mock_response = {
            "data": {
                "addProjectV2ItemById": {
                    "item": None
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        item_id = client.add_issue_to_project(
            "PVT_project123", "I_kwDOABCDEF12345", "github.com"
        )

        assert item_id is None

    def test_add_issue_to_project_returns_none_on_error(self, mock_gh_subprocess):
        """Test add_issue_to_project returns None on GraphQL error."""
        import subprocess

        client = GitHubTicketClient({"github.com": "test_token"})

        mock_gh_subprocess.side_effect = subprocess.CalledProcessError(
            1, "gh", stderr="permission denied"
        )

        item_id = client.add_issue_to_project(
            "PVT_project123", "I_kwDOABCDEF12345", "github.com"
        )

        assert item_id is None

    def test_add_issue_to_project_handles_ghes(self, mock_gh_subprocess):
        """Test add_issue_to_project works with GitHub Enterprise Server."""
        client = GitHubTicketClient({"github.example.com": "test_token"})

        mock_response = {
            "data": {
                "addProjectV2ItemById": {
                    "item": {
                        "id": "PVTI_ghes12345"
                    }
                }
            }
        }
        mock_result = MagicMock()
        mock_result.stdout = json.dumps(mock_response)
        mock_result.returncode = 0
        mock_gh_subprocess.return_value = mock_result

        item_id = client.add_issue_to_project(
            "PVT_project123", "I_kwGHES12345", "github.example.com"
        )

        assert item_id == "PVTI_ghes12345"
        # Verify the hostname was passed correctly
        call_args = mock_gh_subprocess.call_args[0][0]
        assert "--hostname" in call_args
        assert "github.example.com" in call_args
