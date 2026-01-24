"""Unit tests for the GitHub ticket client module."""

import json
import subprocess
from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from src.interfaces import Comment, LinkedPullRequest
from src.ticket_clients.base import NetworkError
from src.ticket_clients.github import GitHubTicketClient
from src.ticket_clients.github_enterprise_3_14 import GitHubEnterprise314Client
from src.ticket_clients.github_enterprise_3_18 import GitHubEnterprise318Client


@pytest.mark.unit
class TestNetworkErrorException:
    """Tests for NetworkError exception class."""

    def test_network_error_can_be_raised(self):
        """Test that NetworkError can be raised with a message."""
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError("TLS handshake timeout")
        assert "TLS handshake timeout" in str(exc_info.value)


@pytest.mark.unit
class TestTimestampNormalization:
    """Tests for timestamp format handling in GitHub API calls."""

    def test_since_timestamp_plus_format_normalized_to_z(self, github_client):
        """Test that +00:00 timestamps are normalized to Z format for GitHub API.

        GitHub's REST API doesn't handle + in URLs correctly (interprets as space).
        We must convert +00:00 to Z format.
        """
        mock_response = json.dumps([])
        timestamp = "2024-01-15T10:30:00+00:00"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, timestamp)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            # MUST use Z format, NOT +00:00 (+ becomes space in URL)
            assert "?since=2024-01-15T10:30:00Z" in endpoint
            assert "+00:00" not in endpoint

    def test_since_timestamp_z_format_unchanged(self, github_client):
        """Test that Z format timestamps are passed through unchanged."""
        mock_response = json.dumps([])
        timestamp = "2024-01-15T10:30:00Z"

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, timestamp)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            assert "?since=2024-01-15T10:30:00Z" in endpoint

    def test_since_timestamp_none_no_parameter(self, github_client):
        """Test that None timestamp doesn't add since parameter."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client.get_comments_since("owner/repo", 42, None)

            call_args = mock_cmd.call_args[0][0]
            endpoint = call_args[1]

            assert "?since=" not in endpoint


@pytest.mark.unit
class TestGetRepoLabels:
    """Tests for GitHubTicketClient.get_repo_labels()."""

    def test_get_repo_labels_returns_list(self, github_client):
        """Test fetching repository labels."""
        mock_response = json.dumps(
            [
                {"name": "bug"},
                {"name": "enhancement"},
                {"name": "researching"},
            ]
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == ["bug", "enhancement", "researching"]

    def test_get_repo_labels_empty_repo(self, github_client):
        """Test fetching labels from repo with no labels."""
        mock_response = json.dumps([])

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == []

    def test_get_repo_labels_handles_error(self, github_client):
        """Test error handling when fetching labels fails."""
        import subprocess

        with patch.object(
            github_client, "_run_gh_command", side_effect=subprocess.CalledProcessError(1, "gh")
        ):
            labels = github_client.get_repo_labels("owner/repo")

        assert labels == []


@pytest.mark.unit
class TestCreateRepoLabel:
    """Tests for GitHubTicketClient.create_repo_label()."""

    def test_create_repo_label_success(self, github_client):
        """Test creating a label successfully."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            result = github_client.create_repo_label(
                "github.com/owner/repo", "researching", "Research in progress", "1D76DB"
            )

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "label" in call_args
        assert "create" in call_args
        assert "researching" in call_args
        assert "--repo" in call_args
        assert "https://github.com/owner/repo" in call_args
        assert "--description" in call_args
        assert "Research in progress" in call_args
        assert "--color" in call_args
        assert "1D76DB" in call_args

    def test_create_repo_label_no_description(self, github_client):
        """Test creating a label without description."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            result = github_client.create_repo_label("owner/repo", "test-label")

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "--description" not in call_args
        assert "--color" not in call_args

    def test_create_repo_label_uses_force_flag(self, github_client):
        """Test that create uses --force to handle existing labels."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.create_repo_label("owner/repo", "test-label")

        call_args = mock_cmd.call_args[0][0]
        assert "--force" in call_args

    def test_create_repo_label_handles_error(self, github_client):
        """Test error handling when label creation fails."""
        import subprocess

        with patch.object(
            github_client, "_run_gh_command", side_effect=subprocess.CalledProcessError(1, "gh")
        ):
            result = github_client.create_repo_label("owner/repo", "test-label")

        assert result is False


@pytest.mark.unit
class TestAddLabel:
    """Tests for GitHubTicketClient.add_label()."""

    def test_add_label_success(self, github_client):
        """Test adding a label successfully."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.add_label("github.com/owner/repo", 123, "researching")

        call_args = mock_cmd.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--add-label" in call_args
        assert "researching" in call_args

    def test_add_label_creates_missing_label(self, github_client):
        """Test that add_label creates the label if it doesn't exist."""
        import subprocess

        # First call fails with "label not found", second call succeeds
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label 'researching' not found"
        error.stdout = ""

        call_count = 0

        def mock_run_gh(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First add_label attempt fails
                raise error
            return ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=mock_run_gh),
            patch.object(github_client, "create_repo_label", return_value=True) as mock_create,
        ):
            github_client.add_label("github.com/owner/repo", 123, "researching")

        # Verify create_repo_label was called
        mock_create.assert_called_once_with("github.com/owner/repo", "researching")
        # Verify add_label was retried
        assert call_count == 2

    def test_add_label_raises_when_label_creation_fails(self, github_client):
        """Test that add_label raises when label creation fails."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label 'researching' not found"
        error.stdout = ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=error),
            patch.object(github_client, "create_repo_label", return_value=False),
        ):
            with pytest.raises(RuntimeError, match="Failed to create label"):
                github_client.add_label("github.com/owner/repo", 123, "researching")

    def test_add_label_raises_on_other_errors(self, github_client):
        """Test that add_label re-raises non-label errors."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "permission denied"
        error.stdout = ""

        with patch.object(github_client, "_run_gh_command", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client.add_label("github.com/owner/repo", 123, "researching")

    def test_add_label_handles_does_not_exist_error(self, github_client):
        """Test that add_label handles 'does not exist' error variant."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label does not exist"
        error.stdout = ""

        call_count = 0

        def mock_run_gh(args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error
            return ""

        with (
            patch.object(github_client, "_run_gh_command", side_effect=mock_run_gh),
            patch.object(github_client, "create_repo_label", return_value=True) as mock_create,
        ):
            github_client.add_label("github.com/owner/repo", 123, "test-label")

        mock_create.assert_called_once()


@pytest.mark.unit
class TestGetIssueBody:
    """Tests for GitHubTicketClient.get_ticket_body()."""

    def test_get_ticket_body_returns_body_text(self, github_client):
        """Test fetching issue body returns the body text."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {"body": "This is the issue description.\n\nWith multiple lines."}
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body == "This is the issue description.\n\nWith multiple lines."

    def test_get_ticket_body_returns_none_for_nonexistent_issue(self, github_client):
        """Test that None is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 99999)

        assert body is None

    def test_get_ticket_body_returns_none_on_empty_body(self, github_client):
        """Test handling of issue with no body."""
        mock_response = {"data": {"repository": {"issue": {"body": None}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body is None

    def test_get_ticket_body_returns_empty_string(self, github_client):
        """Test handling of issue with empty string body."""
        mock_response = {"data": {"repository": {"issue": {"body": ""}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body == ""

    def test_get_ticket_body_handles_api_error(self, github_client):
        """Test that API errors return None."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            body = github_client.get_ticket_body("owner/repo", 42)

        assert body is None

    def test_get_ticket_body_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made."""
        mock_response = {"data": {"repository": {"issue": {"body": "Test body"}}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_ticket_body("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "body" in query
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123


@pytest.mark.unit
class TestGetTicketLabels:
    """Tests for GitHubTicketClient.get_ticket_labels()."""

    def test_get_ticket_labels_returns_multiple_labels(self, github_client):
        """Test fetching issue labels returns a set of label names."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [
                                {"name": "bug"},
                                {"name": "priority:high"},
                                {"name": "yolo"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == {"bug", "priority:high", "yolo"}

    def test_get_ticket_labels_returns_empty_set_for_no_labels(self, github_client):
        """Test that an empty set is returned when issue has no labels."""
        mock_response = {"data": {"repository": {"issue": {"labels": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_returns_empty_set_for_nonexistent_issue(self, github_client):
        """Test that empty set is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 99999)

        assert labels == set()

    def test_get_ticket_labels_returns_empty_set_on_api_error(self, github_client):
        """Test that API errors return empty set."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made with proper structure."""
        mock_response = {
            "data": {"repository": {"issue": {"labels": {"nodes": [{"name": "test"}]}}}}
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_ticket_labels("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "labels(first: 100)" in query
            assert "nodes" in query
            assert "name" in query
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123

    def test_get_ticket_labels_handles_null_label_nodes(self, github_client):
        """Test handling of null entries in label nodes."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [{"name": "valid-label"}, None, {"name": "another-label"}]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("owner/repo", 42)

        assert labels == {"valid-label", "another-label"}


@pytest.mark.unit
class TestGetLastProjectStatusActor:
    """Tests for GitHubTicketClient.get_last_status_actor()."""

    def test_get_last_status_actor_returns_actor(self, github_client):
        """Test that the actor from the most recent timeline event is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "user1"},
                                    "createdAt": "2024-01-10T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "user2"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        # Should return the last actor (most recent is last in list since we used 'last: 10')
        assert actor == "user2"

    def test_get_last_status_actor_returns_none_when_no_events(self, github_client):
        """Test that None is returned when there are no timeline events."""
        mock_response = {"data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        assert actor is None

    def test_get_last_status_actor_returns_none_on_api_error(self, github_client):
        """Test that None is returned and error is logged on API failure."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        assert actor is None

    def test_get_last_status_actor_returns_none_for_nonexistent_issue(self, github_client):
        """Test that None is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 99999)

        assert actor is None

    def test_get_last_status_actor_skips_events_without_actor(self, github_client):
        """Test that events without actor field are skipped."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": {"login": "valid_user"},
                                    "createdAt": "2024-01-10T10:00:00Z",
                                },
                                {
                                    "__typename": "ProjectV2ItemStatusChangedEvent",
                                    "actor": None,  # No actor (e.g., deleted user)
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_last_status_actor("owner/repo", 42)

        # Should return the previous valid actor since the most recent has None
        assert actor == "valid_user"

    def test_get_last_status_actor_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "__typename": "AddedToProjectV2Event",
                                    "actor": {"login": "testuser"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_last_status_actor("test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            # Verify query structure
            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "timelineItems" in query
            assert "ADDED_TO_PROJECT_V2_EVENT" in query
            assert "PROJECT_V2_ITEM_STATUS_CHANGED_EVENT" in query
            assert "actor" in query
            assert "login" in query

            # Verify variables
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123


@pytest.mark.unit
class TestGetLabelActor:
    """Tests for GitHubTicketClient.get_label_actor() method."""

    def test_get_label_actor_returns_actor(self, github_client):
        """Test that the actor who added a specific label is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "bug"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                                {
                                    "actor": {"login": "user2"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor == "user2"

    def test_get_label_actor_returns_none_when_label_not_found(self, github_client):
        """Test that None is returned when the label was never added."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "bug"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_none_when_no_events(self, github_client):
        """Test that None is returned when there are no label events."""
        mock_response = {"data": {"repository": {"issue": {"timelineItems": {"nodes": []}}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_none_on_api_error(self, github_client):
        """Test that None is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        assert actor is None

    def test_get_label_actor_returns_most_recent(self, github_client):
        """Test that the most recent addition of the label is returned."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "timelineItems": {
                            "nodes": [
                                {
                                    "actor": {"login": "user1"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T09:00:00Z",
                                },
                                {
                                    "actor": {"login": "user2"},
                                    "label": {"name": "yolo"},
                                    "createdAt": "2024-01-15T10:00:00Z",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            actor = github_client.get_label_actor("owner/repo", 42, "yolo")

        # Should return the most recent (last in list)
        assert actor == "user2"


@pytest.mark.unit
class TestParseBoardUrl:
    """Tests for GitHubTicketClient._parse_board_url() method."""

    def test_parse_board_url_github_com(self, github_client):
        """Test parsing standard github.com project URL."""
        url = "https://github.com/orgs/myorg/projects/42/views/1"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert project_number == 42

    def test_parse_board_url_without_views(self, github_client):
        """Test parsing URL without /views/ suffix."""
        url = "https://github.com/orgs/testorg/projects/99"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "testorg"
        assert project_number == 99

    def test_parse_board_url_user_project(self, github_client):
        """Test parsing user project URL."""
        url = "https://github.com/users/myuser/projects/5"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "user"
        assert login == "myuser"
        assert project_number == 5

    def test_parse_board_url_invalid_format(self, github_client):
        """Test parsing invalid URL raises ValueError."""
        url = "https://github.com/testorg/testrepo"  # Not a project URL

        import pytest

        with pytest.raises(ValueError, match="Invalid project URL format"):
            github_client._parse_board_url(url)

    def test_parse_board_url_http(self, github_client):
        """Test parsing http:// URL (not https)."""
        url = "http://github.com/orgs/myorg/projects/10"
        hostname, entity_type, login, project_number = github_client._parse_board_url(url)

        assert hostname == "github.com"
        assert entity_type == "organization"
        assert login == "myorg"
        assert project_number == 10


@pytest.mark.unit
class TestTokenManagement:
    """Tests for GitHubTicketClient token management."""

    def test_get_token_for_host_found(self):
        """Test getting token for a configured host."""
        client = GitHubTicketClient(
            tokens={"github.com": "ghp_abc", "custom.github.com": "ghp_xyz"}
        )

        assert client._get_token_for_host("github.com") == "ghp_abc"
        assert client._get_token_for_host("custom.github.com") == "ghp_xyz"

    def test_get_token_for_host_not_found(self):
        """Test getting token for unconfigured host returns None."""
        client = GitHubTicketClient(tokens={"github.com": "ghp_abc"})

        assert client._get_token_for_host("unknown.host.com") is None

    def test_get_token_for_host_empty_tokens(self):
        """Test getting token with empty tokens dict returns None."""
        client = GitHubTicketClient(tokens={})

        assert client._get_token_for_host("github.com") is None

    def test_get_token_for_host_no_tokens(self):
        """Test getting token when tokens is None returns None."""
        client = GitHubTicketClient(tokens=None)

        assert client._get_token_for_host("github.com") is None

    def test_init_with_tokens_dict(self):
        """Test initializing client with tokens dictionary."""
        tokens = {"github.com": "ghp_public", "github.mycompany.com": "ghp_private"}
        client = GitHubTicketClient(tokens=tokens)

        assert client.tokens == tokens

    def test_init_without_tokens(self):
        """Test initializing client without tokens."""
        client = GitHubTicketClient()

        assert client.tokens == {}


@pytest.mark.unit
@pytest.mark.skip_auto_mock_validation
class TestValidateConnection:
    """Tests for GitHubTicketClient.validate_connection() method."""

    def test_validate_connection_success(self, github_client):
        """Test successful connection validation returns True."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.validate_connection("github.com")

        assert result is True

    def test_validate_connection_default_hostname(self, github_client):
        """Test that default hostname is github.com."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.validate_connection()

            # Verify hostname passed to query
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["hostname"] == "github.com"

    def test_validate_connection_custom_hostname(self, github_client):
        """Test validation with custom hostname."""
        mock_response = {"data": {"viewer": {"login": "custom-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            result = github_client.validate_connection("custom.github.com")

            # Verify custom hostname was used
            call_kwargs = mock_query.call_args[1]
            assert call_kwargs["hostname"] == "custom.github.com"
            assert result is True

    def test_validate_connection_no_login_raises_error(self, github_client):
        """Test that empty viewer response raises RuntimeError."""
        mock_response = {"data": {"viewer": {}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Could not retrieve authenticated user"):
                github_client.validate_connection()

    def test_validate_connection_null_viewer_raises_error(self, github_client):
        """Test that null viewer raises RuntimeError."""
        mock_response = {"data": {"viewer": None}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with pytest.raises(RuntimeError, match="Could not retrieve authenticated user"):
                github_client.validate_connection()

    def test_validate_connection_subprocess_error(self, github_client):
        """Test that subprocess errors are converted to RuntimeError."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "authentication required"
        error.stdout = ""

        with patch.object(github_client, "_execute_graphql_query", side_effect=error):
            with pytest.raises(RuntimeError, match="authentication required"):
                github_client.validate_connection()

    def test_validate_connection_value_error(self, github_client):
        """Test that ValueError from GraphQL is converted to RuntimeError."""
        with patch.object(
            github_client,
            "_execute_graphql_query",
            side_effect=ValueError("GraphQL errors: Bad credentials"),
        ):
            with pytest.raises(RuntimeError, match="Bad credentials"):
                github_client.validate_connection()

    def test_validate_connection_makes_viewer_query(self, github_client):
        """Test that the correct viewer query is made."""
        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.validate_connection()

            # Verify query contains viewer request
            query = mock_query.call_args[0][0]
            assert "viewer" in query
            assert "login" in query

    def test_validate_connection_quiet_logs_debug(self, github_client, caplog):
        """Test that quiet=True logs at DEBUG level instead of INFO."""
        import logging

        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with caplog.at_level(logging.DEBUG):
                github_client.validate_connection("github.com", quiet=True)

        # Verify the success message was logged
        assert "GitHub authentication successful" in caplog.text
        # Verify it was logged at DEBUG level, not INFO
        auth_records = [
            r for r in caplog.records if "authentication successful" in r.message
        ]
        assert len(auth_records) == 1
        assert auth_records[0].levelno == logging.DEBUG

    def test_validate_connection_default_logs_info(self, github_client, caplog):
        """Test that default (quiet=False) logs at INFO level."""
        import logging

        mock_response = {"data": {"viewer": {"login": "test-user"}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            with caplog.at_level(logging.DEBUG):
                github_client.validate_connection("github.com")

        # Verify the success message was logged at INFO level
        auth_records = [
            r for r in caplog.records if "authentication successful" in r.message
        ]
        assert len(auth_records) == 1
        assert auth_records[0].levelno == logging.INFO


@pytest.mark.unit
class TestGetTokenScopes:
    """Tests for GitHubTicketClient._get_token_scopes() method."""

    def test_get_token_scopes_parses_header(self, github_client):
        """Test parsing X-OAuth-Scopes header."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == {"repo", "read:org", "project"}

    def test_get_token_scopes_empty_scopes(self, github_client):
        """Test handling empty X-OAuth-Scopes header."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: \n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == set()

    def test_get_token_scopes_no_header_returns_none(self, github_client):
        """Test that missing header returns None (fine-grained PAT)."""
        mock_output = 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes is None

    def test_get_token_scopes_case_insensitive_header(self, github_client):
        """Test that header matching is case-insensitive."""
        mock_output = 'HTTP/2.0 200 OK\nx-oauth-scopes: repo, project\n\n{"login": "test"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            scopes = github_client._get_token_scopes("github.com")

        assert scopes == {"repo", "project"}

    def test_get_token_scopes_uses_token(self, github_client):
        """Test that configured token is used in API call."""
        mock_output = "HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{}"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client._get_token_scopes("github.com")

            call_kwargs = mock_run.call_args[1]
            assert "GITHUB_TOKEN" in call_kwargs["env"]
            assert call_kwargs["env"]["GITHUB_TOKEN"] == "test-token"

    def test_get_token_scopes_custom_hostname(self, github_client):
        """Test scope fetching with custom hostname."""
        mock_output = "HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{}"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client._get_token_scopes("custom.github.com")

            call_args = mock_run.call_args[0][0]
            assert "--hostname" in call_args
            assert "custom.github.com" in call_args

    def test_get_token_scopes_api_error_returns_none(self, github_client):
        """Test that API errors return None."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="API error")
            scopes = github_client._get_token_scopes("github.com")

        assert scopes is None


@pytest.mark.unit
@pytest.mark.skip_auto_mock_validation
class TestValidateScopes:
    """Tests for GitHubTicketClient.validate_scopes() method."""

    def test_validate_scopes_success(self, github_client):
        """Test successful scope validation with all required scopes."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            result = github_client.validate_scopes("github.com")

        assert result is True

    def test_validate_scopes_missing_scopes_raises_error(self, github_client):
        """Test that missing required scopes raises RuntimeError."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError, match="should ONLY have these scopes"):
                github_client.validate_scopes("github.com")

    def test_validate_scopes_fine_grained_pat_raises_error(self, github_client):
        """Test that fine-grained PAT (no X-OAuth-Scopes header) raises RuntimeError."""
        mock_output = 'HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "fine-grained PAT" in error_msg.lower() or "could not verify" in error_msg.lower()
        assert "classic Personal Access Token" in error_msg

    def test_validate_scopes_fine_grained_pat_prefix_detected_early(self, github_client):
        """Test that fine-grained PAT is detected by prefix before API call."""
        # Set a fine-grained PAT token
        github_client.tokens["github.com"] = "github_pat_abc123xyz"

        # Should fail immediately without making API call
        with pytest.raises(RuntimeError) as exc_info:
            github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "Fine-grained PAT detected" in error_msg
        assert "github_pat_" in error_msg
        assert "classic Personal Access Token" in error_msg

    def test_validate_scopes_classic_pat_prefix_allowed(self, github_client):
        """Test that classic PAT prefix (ghp_) passes prefix check."""
        github_client.tokens["github.com"] = "ghp_abc123xyz"
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            result = github_client.validate_scopes("github.com")

        assert result is True

    def test_validate_scopes_custom_hostname(self, github_client):
        """Test scope validation with custom hostname."""
        mock_output = (
            'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo, read:org, project\n\n{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            github_client.validate_scopes("custom.github.com")

            # Verify --hostname flag was passed
            call_args = mock_run.call_args[0][0]
            assert "--hostname" in call_args
            assert "custom.github.com" in call_args

    def test_validate_scopes_error_message_lists_missing_scopes(self, github_client):
        """Test that error message clearly lists which scopes are missing."""
        mock_output = 'HTTP/2.0 200 OK\nX-OAuth-Scopes: repo\n\n{"login": "test-user"}'

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "project" in error_msg
            assert "read:org" in error_msg

    def test_validate_scopes_api_error_raises(self, github_client):
        """Test that API errors raise RuntimeError (fail closed for security)."""
        import subprocess

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="API error")
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

        error_msg = str(exc_info.value)
        assert "Could not verify token scopes" in error_msg

    def test_validate_scopes_required_scopes_constant(self, github_client):
        """Test that REQUIRED_SCOPES contains expected values."""
        assert {"repo", "read:org", "project"} == github_client.REQUIRED_SCOPES

    def test_validate_scopes_excessive_scopes_raises_error(self, github_client):
        """Test that excessive scopes raise RuntimeError."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError, match="should ONLY have these scopes"):
                github_client.validate_scopes("github.com")

    def test_validate_scopes_excessive_scopes_error_provides_guidance(self, github_client):
        """Test that error message provides guidance on required scopes."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org, delete_repo\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "project" in error_msg
            assert "read:org" in error_msg
            assert "repo" in error_msg

    def test_validate_scopes_multiple_excessive_scopes(self, github_client):
        """Test detection of multiple excessive scopes."""
        mock_output = (
            "HTTP/2.0 200 OK\n"
            "X-OAuth-Scopes: repo, read:org, project, admin:org, workflow, user\n"
            "\n"
            '{"login": "test-user"}'
        )

        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = mock_output
            mock_run.return_value.returncode = 0
            with pytest.raises(RuntimeError) as exc_info:
                github_client.validate_scopes("github.com")

            error_msg = str(exc_info.value)
            assert "should ONLY have these scopes" in error_msg
            assert "too many or too few" in error_msg

    def test_validate_scopes_excessive_scopes_constant(self, github_client):
        """Test that EXCESSIVE_SCOPES contains expected dangerous scopes."""
        expected = {
            "admin:org",
            "delete_repo",
            "admin:org_hook",
            "admin:repo_hook",
            "admin:public_key",
            "admin:gpg_key",
            "write:org",
            "workflow",
            "delete:packages",
            "codespace",
            "user",
        }
        assert expected == github_client.EXCESSIVE_SCOPES


@pytest.mark.unit
class TestGetLinkedPRs:
    """Tests for GitHubTicketClient.get_linked_prs() method."""

    def test_get_linked_prs_returns_pr_list(self, github_client):
        """Test that linked PRs are returned correctly."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 123,
                                    "url": "https://github.com/owner/repo/pull/123",
                                    "body": "Closes #42\n\nSome description",
                                    "state": "OPEN",
                                    "merged": False,
                                    "headRefName": "42-feature-branch",
                                },
                                {
                                    "number": 456,
                                    "url": "https://github.com/owner/repo/pull/456",
                                    "body": "Fixes #42",
                                    "state": "MERGED",
                                    "merged": True,
                                    "headRefName": "42-other-branch",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert len(prs) == 2
        assert prs[0].number == 123
        assert prs[0].url == "https://github.com/owner/repo/pull/123"
        assert prs[0].body == "Closes #42\n\nSome description"
        assert prs[0].state == "OPEN"
        assert prs[0].merged is False
        assert prs[0].branch_name == "42-feature-branch"
        assert prs[1].number == 456
        assert prs[1].merged is True
        assert prs[1].branch_name == "42-other-branch"

    def test_get_linked_prs_returns_empty_list_when_no_prs(self, github_client):
        """Test that empty list is returned when there are no linked PRs."""
        mock_response = {
            "data": {"repository": {"issue": {"closedByPullRequestsReferences": {"nodes": []}}}}
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert prs == []

    def test_get_linked_prs_returns_empty_list_on_nonexistent_issue(self, github_client):
        """Test that empty list is returned when issue doesn't exist."""
        mock_response = {"data": {"repository": {"issue": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 99999)

        assert prs == []

    def test_get_linked_prs_returns_empty_list_on_api_error(self, github_client):
        """Test that empty list is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert prs == []

    def test_get_linked_prs_skips_null_nodes(self, github_client):
        """Test that null nodes in the response are skipped."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                None,
                                {
                                    "number": 123,
                                    "url": "https://github.com/owner/repo/pull/123",
                                    "body": "Closes #42",
                                    "state": "OPEN",
                                    "merged": False,
                                    "headRefName": "42-branch",
                                },
                                None,
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            prs = github_client.get_linked_prs("github.com/owner/repo", 42)

        assert len(prs) == 1
        assert prs[0].number == 123
        assert prs[0].branch_name == "42-branch"


@pytest.mark.unit
class TestRemovePRIssueLink:
    """Tests for GitHubTicketClient.remove_pr_issue_link() method."""

    def test_remove_pr_issue_link_removes_closes_keyword(self, github_client):
        """Test that 'closes' keyword is removed from PR body."""
        pr_response = {
            "data": {
                "repository": {"pullRequest": {"body": "This PR closes #42 and adds new features."}}
            }
        }

        with (
            patch.object(github_client, "_execute_graphql_query", return_value=pr_response),
            patch.object(github_client, "_run_gh_command") as mock_run,
        ):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is True
        # Verify the new body was passed to gh pr edit
        call_args = mock_run.call_args[0][0]
        assert "pr" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--body" in call_args
        # The body should have "closes " removed but "#42" preserved
        body_idx = call_args.index("--body") + 1
        new_body = call_args[body_idx]
        assert "closes" not in new_body.lower()
        assert "#42" in new_body

    def test_remove_pr_issue_link_handles_various_keywords(self, github_client):
        """Test that various linking keywords are removed."""
        test_cases = [
            ("Fixes #42", "#42"),
            ("fixes: #42", "#42"),
            ("CLOSES #42", "#42"),
            ("Resolves #42", "#42"),
            ("This PR closes #42", "This PR #42"),
            ("Fix #42 and close #99", "#42 and close #99"),  # Removes "Fix" keyword for #42
        ]

        for original, expected in test_cases:
            result = github_client._remove_closes_keyword(original, 42)
            assert result == expected, (
                f"Failed for '{original}': got '{result}' expected '{expected}'"
            )

    def test_remove_pr_issue_link_returns_false_when_no_keyword(self, github_client):
        """Test that False is returned when no linking keyword is found."""
        pr_response = {
            "data": {
                "repository": {
                    "pullRequest": {"body": "This PR is related to #42 but doesn't close it."}
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=pr_response):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is False

    def test_remove_pr_issue_link_returns_false_when_pr_not_found(self, github_client):
        """Test that False is returned when PR doesn't exist."""
        pr_response = {"data": {"repository": {"pullRequest": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=pr_response):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 99999, 42)

        assert result is False

    def test_remove_pr_issue_link_returns_false_on_api_error(self, github_client):
        """Test that False is returned on API error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.remove_pr_issue_link("github.com/owner/repo", 123, 42)

        assert result is False


@pytest.mark.unit
class TestRemoveClosesKeyword:
    """Tests for GitHubTicketClient._remove_closes_keyword() helper method."""

    def test_remove_closes_keyword_close(self, github_client):
        """Test removing 'close' keyword."""
        result = github_client._remove_closes_keyword("close #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_closes(self, github_client):
        """Test removing 'closes' keyword."""
        result = github_client._remove_closes_keyword("closes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_closed(self, github_client):
        """Test removing 'closed' keyword."""
        result = github_client._remove_closes_keyword("closed #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fix(self, github_client):
        """Test removing 'fix' keyword."""
        result = github_client._remove_closes_keyword("fix #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fixes(self, github_client):
        """Test removing 'fixes' keyword."""
        result = github_client._remove_closes_keyword("fixes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_fixed(self, github_client):
        """Test removing 'fixed' keyword."""
        result = github_client._remove_closes_keyword("fixed #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolve(self, github_client):
        """Test removing 'resolve' keyword."""
        result = github_client._remove_closes_keyword("resolve #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolves(self, github_client):
        """Test removing 'resolves' keyword."""
        result = github_client._remove_closes_keyword("resolves #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_resolved(self, github_client):
        """Test removing 'resolved' keyword."""
        result = github_client._remove_closes_keyword("resolved #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_with_colon(self, github_client):
        """Test removing keyword with colon."""
        result = github_client._remove_closes_keyword("Fixes: #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_case_insensitive(self, github_client):
        """Test that keyword matching is case insensitive."""
        result = github_client._remove_closes_keyword("CLOSES #123", 123)
        assert result == "#123"

        result = github_client._remove_closes_keyword("Fixes #123", 123)
        assert result == "#123"

    def test_remove_closes_keyword_preserves_surrounding_text(self, github_client):
        """Test that surrounding text is preserved."""
        result = github_client._remove_closes_keyword(
            "This PR closes #123 by refactoring the code.", 123
        )
        assert result == "This PR #123 by refactoring the code."

    def test_remove_closes_keyword_only_removes_specified_issue(self, github_client):
        """Test that only the specified issue number is affected."""
        result = github_client._remove_closes_keyword("closes #123 and fixes #456", 123)
        assert result == "#123 and fixes #456"

    def test_remove_closes_keyword_no_change_when_different_issue(self, github_client):
        """Test that body is unchanged when different issue number."""
        original = "closes #456"
        result = github_client._remove_closes_keyword(original, 123)
        assert result == original

    def test_remove_closes_keyword_no_change_when_no_keyword(self, github_client):
        """Test that body is unchanged when no linking keyword."""
        original = "Related to #123"
        result = github_client._remove_closes_keyword(original, 123)
        assert result == original


@pytest.mark.unit
class TestClosePr:
    """Tests for GitHubTicketClient.close_pr() method."""

    def test_close_pr_success(self, github_client):
        """Test successfully closing a PR."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            result = github_client.close_pr("github.com/owner/repo", 123)

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["pr", "close", "123", "--repo", "https://github.com/owner/repo"]

    def test_close_pr_returns_false_on_error(self, github_client):
        """Test that False is returned when gh command fails."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "PR is already closed"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.close_pr("github.com/owner/repo", 123)

        assert result is False

    def test_close_pr_uses_correct_repo_reference(self, github_client):
        """Test that the full repo URL is used for GHES compatibility."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.close_pr("github.example.com/myorg/myrepo", 456)

        call_args = mock_run.call_args[0][0]
        assert "--repo" in call_args
        repo_idx = call_args.index("--repo") + 1
        assert call_args[repo_idx] == "https://github.example.com/myorg/myrepo"

    def test_close_pr_passes_repo_for_hostname_lookup(self, github_client):
        """Test that repo is passed for hostname lookup."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.close_pr("github.com/owner/repo", 99)

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["repo"] == "github.com/owner/repo"


@pytest.mark.unit
class TestDeleteBranch:
    """Tests for GitHubTicketClient.delete_branch() method."""

    def test_delete_branch_success(self, github_client):
        """Test successfully deleting a branch."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            result = github_client.delete_branch("github.com/owner/repo", "feature-branch")

        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ["api", "repos/owner/repo/git/refs/heads/feature-branch", "-X", "DELETE"]

    def test_delete_branch_returns_false_when_not_found(self, github_client):
        """Test that False is returned when branch doesn't exist."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "HTTP 404: Not Found"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.delete_branch("github.com/owner/repo", "nonexistent-branch")

        assert result is False

    def test_delete_branch_returns_false_on_error(self, github_client):
        """Test that False is returned on API error."""
        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "API error"
        with patch.object(github_client, "_run_gh_command", side_effect=error):
            result = github_client.delete_branch("github.com/owner/repo", "feature-branch")

        assert result is False

    def test_delete_branch_handles_slashes_in_name(self, github_client):
        """Test that branch names with slashes are URL-encoded."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.com/owner/repo", "feature/my-feature")

        call_args = mock_run.call_args[0][0]
        # Branch name with slash should be URL-encoded
        assert call_args == ["api", "repos/owner/repo/git/refs/heads/feature%2Fmy-feature", "-X", "DELETE"]

    def test_delete_branch_uses_hostname_for_ghes(self, github_client):
        """Test that hostname is passed for GHES compatibility."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.example.com/myorg/myrepo", "feature-branch")

        mock_run.assert_called_once()
        assert mock_run.call_args[1]["hostname"] == "github.example.com"

    def test_delete_branch_parses_repo_correctly(self, github_client):
        """Test that repo is parsed correctly for API endpoint."""
        with patch.object(github_client, "_run_gh_command") as mock_run:
            github_client.delete_branch("github.com/my-org/my-repo", "fix-bug")

        call_args = mock_run.call_args[0][0]
        assert "repos/my-org/my-repo/git/refs/heads/fix-bug" in call_args[1]


@pytest.mark.unit
class TestGetPrState:
    """Tests for GitHubTicketClient.get_pr_state() method."""

    def test_get_pr_state_returns_open(self, github_client):
        """Test that OPEN state is returned for an open PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "OPEN",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "OPEN"

    def test_get_pr_state_returns_closed(self, github_client):
        """Test that CLOSED state is returned for a closed PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "CLOSED",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "CLOSED"

    def test_get_pr_state_returns_merged(self, github_client):
        """Test that MERGED state is returned for a merged PR."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "CLOSED",
                        "merged": True,
                    }
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result == "MERGED"

    def test_get_pr_state_returns_none_when_pr_not_found(self, github_client):
        """Test that None is returned when PR doesn't exist."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": None
                }
            }
        }
        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.get_pr_state("github.com/owner/repo", 999)

        assert result is None

    def test_get_pr_state_returns_none_on_error(self, github_client):
        """Test that None is returned on API error (fail-safe)."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.get_pr_state("github.com/owner/repo", 123)

        assert result is None

    def test_get_pr_state_queries_correct_repo(self, github_client):
        """Test that the correct repo is queried."""
        mock_response = {
            "data": {
                "repository": {
                    "pullRequest": {
                        "state": "OPEN",
                        "merged": False,
                    }
                }
            }
        }
        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_pr_state("github.com/myorg/myrepo", 456)

        # Check the variables passed to the query
        call_args = mock_query.call_args
        variables = call_args[0][1]
        assert variables["owner"] == "myorg"
        assert variables["repo"] == "myrepo"
        assert variables["prNumber"] == 456


@pytest.mark.unit
class TestLinkedPullRequest:
    """Tests for LinkedPullRequest dataclass."""

    def test_linked_pr_creation(self):
        """Test creating a LinkedPullRequest instance."""
        pr = LinkedPullRequest(
            number=123,
            url="https://github.com/owner/repo/pull/123",
            body="Closes #42",
            state="OPEN",
            merged=False,
        )

        assert pr.number == 123
        assert pr.url == "https://github.com/owner/repo/pull/123"
        assert pr.body == "Closes #42"
        assert pr.state == "OPEN"
        assert pr.merged is False
        assert pr.branch_name is None

    def test_linked_pr_with_branch_name(self):
        """Test creating a LinkedPullRequest with branch_name."""
        pr = LinkedPullRequest(
            number=123,
            url="https://github.com/owner/repo/pull/123",
            body="Closes #42",
            state="OPEN",
            merged=False,
            branch_name="42-feature-branch",
        )

        assert pr.number == 123
        assert pr.branch_name == "42-feature-branch"

    def test_linked_pr_merged_state(self):
        """Test LinkedPullRequest with merged state."""
        pr = LinkedPullRequest(
            number=456,
            url="https://github.com/owner/repo/pull/456",
            body="Fixes #99",
            state="MERGED",
            merged=True,
        )

        assert pr.state == "MERGED"
        assert pr.merged is True


@pytest.mark.unit
class TestGetBoardItems:
    """Tests for GitHubTicketClient.get_board_items() method."""

    def test_get_board_items_returns_list(self, github_client):
        """Test that board items are returned as a list of TicketItem."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "PVTI_item123",
                                    "content": {
                                        "number": 42,
                                        "title": "Test Issue",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": [{"name": "bug"}]},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 5},
                                    },
                                    "fieldValues": {
                                        "nodes": [{"field": {"name": "Status"}, "name": "Research"}]
                                    },
                                }
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            items = github_client.get_board_items("https://github.com/orgs/testorg/projects/1")

        assert len(items) == 1
        assert items[0].ticket_id == 42
        assert items[0].title == "Test Issue"
        assert items[0].status == "Research"

    def test_get_board_items_handles_pagination(self, github_client):
        """Test that pagination is handled correctly."""
        page1 = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                            "nodes": [
                                {
                                    "id": "PVTI_1",
                                    "content": {
                                        "number": 1,
                                        "title": "Issue 1",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": []},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 0},
                                    },
                                    "fieldValues": {"nodes": []},
                                }
                            ],
                        }
                    }
                }
            }
        }
        page2 = {
            "data": {
                "organization": {
                    "projectV2": {
                        "items": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [
                                {
                                    "id": "PVTI_2",
                                    "content": {
                                        "number": 2,
                                        "title": "Issue 2",
                                        "state": "OPEN",
                                        "stateReason": None,
                                        "repository": {"nameWithOwner": "owner/repo"},
                                        "labels": {"nodes": []},
                                        "closedByPullRequestsReferences": {"nodes": []},
                                        "comments": {"totalCount": 0},
                                    },
                                    "fieldValues": {"nodes": []},
                                }
                            ],
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [page1, page2]
            items = github_client.get_board_items("https://github.com/orgs/testorg/projects/1")

        assert len(items) == 2
        assert items[0].ticket_id == 1
        assert items[1].ticket_id == 2


@pytest.mark.unit
class TestGetBoardMetadata:
    """Tests for GitHubTicketClient.get_board_metadata() method."""

    def test_get_board_metadata_returns_project_info(self, github_client):
        """Test fetching project metadata including status field."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_123",
                        "fields": {
                            "nodes": [
                                {
                                    "id": "PVTSSF_456",
                                    "name": "Status",
                                    "options": [
                                        {"id": "opt1", "name": "Backlog"},
                                        {"id": "opt2", "name": "Research"},
                                        {"id": "opt3", "name": "Plan"},
                                    ],
                                }
                            ]
                        },
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            metadata = github_client.get_board_metadata(
                "https://github.com/orgs/testorg/projects/1"
            )

        assert metadata["project_id"] == "PVT_123"
        assert metadata["status_field_id"] == "PVTSSF_456"
        assert metadata["status_options"] == {
            "Backlog": "opt1",
            "Research": "opt2",
            "Plan": "opt3",
        }

    def test_get_board_metadata_handles_missing_status_field(self, github_client):
        """Test handling when Status field is not found."""
        mock_response = {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_123",
                        "fields": {
                            "nodes": [
                                {
                                    "id": "PVTSSF_789",
                                    "name": "Priority",
                                    "options": [],
                                }
                            ]
                        },
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            metadata = github_client.get_board_metadata(
                "https://github.com/orgs/testorg/projects/1"
            )

        assert metadata["project_id"] == "PVT_123"
        assert metadata["status_field_id"] is None
        assert metadata["status_options"] == {}


@pytest.mark.unit
class TestUpdateItemStatus:
    """Tests for GitHubTicketClient.update_item_status() method."""

    def test_update_item_status_success(self, github_client):
        """Test successfully updating item status."""
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                                {"id": "opt2", "name": "Research"},
                            ],
                        },
                    }
                }
            }
        }
        mutation_response = {
            "data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_789"}}}
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [item_query_response, mutation_response]
            github_client.update_item_status("PVTI_789", "Research")

        assert mock_query.call_count == 2

    def test_update_item_status_raises_on_invalid_status(self, github_client):
        """Test that ValueError is raised for non-existent status."""
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                            ],
                        },
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=item_query_response
        ):
            with pytest.raises(ValueError, match="Status 'NonExistent' not found"):
                github_client.update_item_status("PVTI_789", "NonExistent")

    def test_update_item_status_accepts_hostname_kwarg(self, github_client):
        """Test that update_item_status accepts hostname keyword argument.

        This ensures signature compatibility with GitHubClientBase for GHES support.
        """
        item_query_response = {
            "data": {
                "node": {
                    "project": {
                        "id": "PVT_123",
                        "field": {
                            "id": "PVTSSF_456",
                            "options": [
                                {"id": "opt1", "name": "Backlog"},
                                {"id": "opt2", "name": "Research"},
                            ],
                        },
                    }
                }
            }
        }
        mutation_response = {
            "data": {"updateProjectV2ItemFieldValue": {"projectV2Item": {"id": "PVTI_789"}}}
        }

        with patch.object(github_client, "_execute_graphql_query") as mock_query:
            mock_query.side_effect = [item_query_response, mutation_response]
            # This call pattern matches how Daemon calls the method
            github_client.update_item_status("PVTI_789", "Research", hostname="github.com")

        assert mock_query.call_count == 2


@pytest.mark.unit
class TestArchiveItem:
    """Tests for GitHubTicketClient.archive_item() method."""

    def test_archive_item_success(self, github_client):
        """Test successfully archiving an item."""
        mock_response = {"data": {"archiveProjectV2Item": {"item": {"id": "PVTI_123"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            result = github_client.archive_item("PVT_project", "PVTI_123")

        assert result is True

    def test_archive_item_failure(self, github_client):
        """Test archive_item returns False on error."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            result = github_client.archive_item("PVT_project", "PVTI_123")

        assert result is False

    def test_archive_item_accepts_hostname_kwarg(self, github_client):
        """Test that archive_item accepts hostname keyword argument.

        This ensures signature compatibility with GitHubClientBase for GHES support.
        """
        mock_response = {"data": {"archiveProjectV2Item": {"item": {"id": "PVTI_123"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            # This call pattern matches how Daemon calls the method
            result = github_client.archive_item("PVT_project", "PVTI_123", hostname="github.com")

        assert result is True


@pytest.mark.unit
class TestRemoveLabel:
    """Tests for GitHubTicketClient.remove_label() method."""

    def test_remove_label_success(self, github_client):
        """Test successfully removing a label."""
        with patch.object(github_client, "_run_gh_command", return_value="") as mock_cmd:
            github_client.remove_label("github.com/owner/repo", 123, "bug")

        call_args = mock_cmd.call_args[0][0]
        assert "issue" in call_args
        assert "edit" in call_args
        assert "123" in call_args
        assert "--remove-label" in call_args
        assert "bug" in call_args

    def test_remove_label_handles_missing_label(self, github_client):
        """Test that removing a non-existent label doesn't raise."""
        import subprocess

        error = subprocess.CalledProcessError(1, "gh")
        error.stderr = "label not found"
        error.stdout = ""

        with patch.object(github_client, "_run_gh_command", side_effect=error):
            # Should not raise
            github_client.remove_label("github.com/owner/repo", 123, "nonexistent")


@pytest.mark.unit
class TestParseRepo:
    """Tests for GitHubTicketClient._parse_repo() method."""

    def test_parse_repo_github_com(self, github_client):
        """Test parsing github.com repo format."""
        hostname, owner, repo = github_client._parse_repo("github.com/owner/repo")

        assert hostname == "github.com"
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_repo_with_custom_hostname(self, github_client):
        """Test parsing repo format with custom hostname."""
        hostname, owner, repo = github_client._parse_repo("custom.github.com/org/project")

        assert hostname == "custom.github.com"
        assert owner == "org"
        assert repo == "project"

    def test_parse_repo_legacy_format(self, github_client):
        """Test parsing legacy owner/repo format."""
        hostname, owner, repo = github_client._parse_repo("owner/repo")

        assert hostname == "github.com"
        assert owner == "owner"
        assert repo == "repo"


@pytest.mark.unit
class TestGetHostnameForRepo:
    """Tests for GitHubTicketClient._get_hostname_for_repo() method."""

    def test_get_hostname_from_repo_string(self, github_client):
        """Test extracting hostname from repo string."""
        hostname = github_client._get_hostname_for_repo("custom.github.com/owner/repo")

        assert hostname == "custom.github.com"

    def test_get_hostname_from_cache(self, github_client):
        """Test getting hostname from cache for legacy format."""
        github_client._repo_host_map["owner/repo"] = "cached.github.com"

        hostname = github_client._get_hostname_for_repo("owner/repo")

        assert hostname == "cached.github.com"

    def test_get_hostname_defaults_to_github_com(self, github_client):
        """Test default hostname is github.com."""
        hostname = github_client._get_hostname_for_repo("unknown/repo")

        assert hostname == "github.com"


@pytest.mark.unit
class TestGetRepoRef:
    """Tests for GitHubTicketClient._get_repo_ref() method."""

    def test_get_repo_ref_returns_https_url(self, github_client):
        """Test that _get_repo_ref returns HTTPS URL."""
        result = github_client._get_repo_ref("github.com/owner/repo")

        assert result == "https://github.com/owner/repo"

    def test_get_repo_ref_preserves_hostname(self, github_client):
        """Test that custom hostname is preserved."""
        result = github_client._get_repo_ref("custom.github.com/owner/repo")

        assert result == "https://custom.github.com/owner/repo"


@pytest.mark.unit
class TestAuthenticationErrorHandling:
    """Tests for authentication error handling in _run_gh_command."""

    def test_auth_error_gh_auth_login_simple(self, github_client):
        """Test that auth error produces simple message in non-debug mode."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="To get started with GitHub CLI, please run:  gh auth login"
        )

        with patch("subprocess.run", side_effect=error):
            with patch("src.ticket_clients.github.is_debug_mode", return_value=False):
                with pytest.raises(RuntimeError) as exc_info:
                    github_client._run_gh_command(["api", "user"])

                error_msg = str(exc_info.value)
                assert "GitHub authentication failed" in error_msg
                assert "GITHUB_TOKEN" in error_msg
                # Simple mode should NOT include detailed error
                assert "gh auth login" not in error_msg

    def test_auth_error_gh_auth_login_debug(self, github_client):
        """Test that auth error produces rich message in debug mode."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="To get started with GitHub CLI, please run:  gh auth login"
        )

        with patch("subprocess.run", side_effect=error):
            with patch("src.ticket_clients.github.is_debug_mode", return_value=True):
                with pytest.raises(RuntimeError) as exc_info:
                    github_client._run_gh_command(["api", "user"])

                error_msg = str(exc_info.value)
                assert "GitHub authentication failed" in error_msg
                assert "GITHUB_TOKEN" in error_msg
                assert "gh auth login" in error_msg

    def test_auth_error_unauthorized(self, github_client):
        """Test that unauthorized error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="401 Unauthorized")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg
            assert "GITHUB_TOKEN" in error_msg

    def test_auth_error_not_logged_in(self, github_client):
        """Test that 'not logged in' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="You are not logged in to any GitHub hosts"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_auth_error_no_token(self, github_client):
        """Test that 'no token' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="no token found")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_auth_error_authentication_required(self, github_client):
        """Test that 'authentication' error produces user-friendly message."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="authentication required")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            error_msg = str(exc_info.value)
            assert "GitHub authentication failed" in error_msg

    def test_non_auth_error_raises_original(self, github_client):
        """Test that non-authentication errors are re-raised as-is."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="some other error: network timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_empty_stderr(self, github_client):
        """Test that empty stderr doesn't cause errors."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="")

        with patch("subprocess.run", side_effect=error):
            # Should raise the original error since no auth indicators
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_none_stderr(self, github_client):
        """Test that None stderr doesn't cause errors."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr=None)

        with patch("subprocess.run", side_effect=error):
            # Should raise the original error since no auth indicators
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_auth_error_includes_hostname(self, github_client):
        """Test that error message includes hostname."""
        import subprocess

        error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="gh auth login")

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(RuntimeError) as exc_info:
                github_client._run_gh_command(["api", "user"], hostname="github.mycompany.com")

            error_msg = str(exc_info.value)
            assert "github.mycompany.com" in error_msg


@pytest.mark.unit
class TestNetworkErrorDetection:
    """Tests for NetworkError detection in _run_gh_command."""

    def test_tls_handshake_timeout_raises_network_error(self, github_client):
        """Test that TLS handshake timeout raises NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="dial tcp: TLS handshake timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError) as exc_info:
                github_client._run_gh_command(["api", "user"])

            assert "network error" in str(exc_info.value).lower()

    def test_connection_timeout_raises_network_error(self, github_client):
        """Test that connection timeout raises NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="connection timeout: unable to reach server"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_connection_refused_raises_network_error(self, github_client):
        """Test that connection refused raises NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="connection refused"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_io_timeout_raises_network_error(self, github_client):
        """Test that i/o timeout raises NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="read: i/o timeout"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_dial_tcp_error_raises_network_error(self, github_client):
        """Test that Go network dial errors raise NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="dial tcp: lookup api.github.com: no such host"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_no_such_host_raises_network_error(self, github_client):
        """Test that DNS resolution failures raise NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="no such host: api.github.com"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_temporary_failure_raises_network_error(self, github_client):
        """Test that temporary DNS failures raise NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="temporary failure in name resolution"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_network_error_generic_raises_network_error(self, github_client):
        """Test that generic network error message raises NetworkError."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="network error: unable to reach GitHub"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])

    def test_non_network_error_raises_called_process_error(self, github_client):
        """Test that non-network errors raise CalledProcessError."""
        import subprocess

        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="unknown error: something else went wrong"
        )

        with patch("subprocess.run", side_effect=error):
            with pytest.raises(subprocess.CalledProcessError):
                github_client._run_gh_command(["api", "user"])

    def test_network_error_takes_precedence_over_auth_error(self, github_client):
        """Test that network errors are detected before auth errors."""
        import subprocess

        from src.ticket_clients.base import NetworkError

        # Error message contains both network and auth indicators
        error = subprocess.CalledProcessError(
            1, ["gh", "api"], stderr="TLS handshake timeout during authentication"
        )

        with patch("subprocess.run", side_effect=error):
            # Should raise NetworkError, not RuntimeError (auth)
            with pytest.raises(NetworkError):
                github_client._run_gh_command(["api", "user"])


@pytest.mark.unit
class TestGetParentIssue:
    """Tests for GitHubTicketClient.get_parent_issue() method."""

    def test_get_parent_issue_returns_parent_number(self, github_client):
        """Test that get_parent_issue returns parent issue number when present."""
        mock_response = {"data": {"repository": {"issue": {"parent": {"number": 42}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent == 42

    def test_get_parent_issue_returns_none_when_no_parent(self, github_client):
        """Test that get_parent_issue returns None when issue has no parent."""
        mock_response = {"data": {"repository": {"issue": {"parent": None}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent is None

    def test_get_parent_issue_returns_none_on_error(self, github_client):
        """Test that get_parent_issue returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query_with_headers", side_effect=Exception("API error")
        ):
            parent = github_client.get_parent_issue("github.com/owner/repo", 123)

        assert parent is None

    def test_get_parent_issue_uses_sub_issues_header(self, github_client):
        """Test that get_parent_issue sends the GraphQL-Features: sub_issues header."""
        mock_response = {"data": {"repository": {"issue": {"parent": None}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            github_client.get_parent_issue("github.com/owner/repo", 123)

            # Verify the headers parameter includes sub_issues
            call_args = mock_query.call_args
            # headers is passed as a keyword argument
            kwargs = call_args.kwargs
            headers = kwargs.get("headers")
            assert headers is not None
            assert "GraphQL-Features: sub_issues" in headers


@pytest.mark.unit
class TestGetPrForIssue:
    """Tests for GitHubTicketClient.get_pr_for_issue() method."""

    def test_get_pr_for_issue_returns_open_pr(self, github_client):
        """Test that get_pr_for_issue returns open PR info."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 99,
                                    "url": "https://github.com/owner/repo/pull/99",
                                    "headRefName": "feature-branch",
                                    "state": "OPEN",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is not None
        assert pr["number"] == 99
        assert pr["url"] == "https://github.com/owner/repo/pull/99"
        assert pr["branch_name"] == "feature-branch"

    def test_get_pr_for_issue_filters_by_state(self, github_client):
        """Test that get_pr_for_issue only returns PRs matching the state filter."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 88,
                                    "url": "https://github.com/owner/repo/pull/88",
                                    "headRefName": "old-branch",
                                    "state": "CLOSED",
                                },
                                {
                                    "number": 99,
                                    "url": "https://github.com/owner/repo/pull/99",
                                    "headRefName": "feature-branch",
                                    "state": "OPEN",
                                },
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        # Should return the OPEN PR, not the CLOSED one
        assert pr is not None
        assert pr["number"] == 99

    def test_get_pr_for_issue_returns_none_when_no_matching_pr(self, github_client):
        """Test that get_pr_for_issue returns None when no PR matches."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "closedByPullRequestsReferences": {
                            "nodes": [
                                {
                                    "number": 88,
                                    "url": "https://github.com/owner/repo/pull/88",
                                    "headRefName": "old-branch",
                                    "state": "CLOSED",
                                }
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None

    def test_get_pr_for_issue_returns_none_on_error(self, github_client):
        """Test that get_pr_for_issue returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None

    def test_get_pr_for_issue_handles_empty_nodes(self, github_client):
        """Test that get_pr_for_issue handles empty PR nodes list."""
        mock_response = {
            "data": {"repository": {"issue": {"closedByPullRequestsReferences": {"nodes": []}}}}
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            pr = github_client.get_pr_for_issue("github.com/owner/repo", 42)

        assert pr is None


@pytest.mark.unit
class TestExecuteGraphqlQueryWithHeaders:
    """Tests for GitHubTicketClient._execute_graphql_query_with_headers() method."""

    def test_execute_graphql_query_with_headers_passes_headers(self, github_client):
        """Test that headers are passed to the gh command."""
        mock_response = json.dumps({"data": {"viewer": {"login": "test"}}})

        with patch.object(github_client, "_run_gh_command", return_value=mock_response) as mock_cmd:
            github_client._execute_graphql_query_with_headers(
                "query { viewer { login } }",
                {},
                ["GraphQL-Features: sub_issues", "Custom-Header: value"],
            )

            # Verify headers are added with -H flags
            call_args = mock_cmd.call_args[0][0]
            assert "-H" in call_args
            assert "GraphQL-Features: sub_issues" in call_args
            assert "Custom-Header: value" in call_args

    def test_execute_graphql_query_with_headers_parses_response(self, github_client):
        """Test that response JSON is correctly parsed."""
        mock_response = json.dumps({"data": {"repository": {"name": "test"}}})

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            result = github_client._execute_graphql_query_with_headers(
                "query { repository { name } }",
                {},
                ["GraphQL-Features: sub_issues"],
            )

        assert result["data"]["repository"]["name"] == "test"

    def test_execute_graphql_query_with_headers_raises_on_errors(self, github_client):
        """Test that GraphQL errors are raised."""
        mock_response = json.dumps(
            {"data": None, "errors": [{"message": "Field 'parent' doesn't exist"}]}
        )

        with patch.object(github_client, "_run_gh_command", return_value=mock_response):
            with pytest.raises(ValueError) as exc_info:
                github_client._execute_graphql_query_with_headers(
                    "query { invalid }",
                    {},
                    ["GraphQL-Features: sub_issues"],
                )

            assert "parent" in str(exc_info.value) or "GraphQL errors" in str(exc_info.value)


@pytest.mark.unit
class TestGetChildIssues:
    """Tests for GitHubTicketClient.get_child_issues() method."""

    def test_get_child_issues_returns_children(self, github_client):
        """Test that get_child_issues returns child issue info."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "subIssues": {
                            "nodes": [
                                {"number": 10, "state": "OPEN"},
                                {"number": 11, "state": "CLOSED"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert len(children) == 2
        assert children[0] == {"number": 10, "state": "OPEN"}
        assert children[1] == {"number": 11, "state": "CLOSED"}

    def test_get_child_issues_returns_empty_when_no_children(self, github_client):
        """Test that get_child_issues returns empty list when no children."""
        mock_response = {"data": {"repository": {"issue": {"subIssues": {"nodes": []}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert children == []

    def test_get_child_issues_returns_empty_on_error(self, github_client):
        """Test that get_child_issues returns empty list on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query_with_headers", side_effect=Exception("API error")
        ):
            children = github_client.get_child_issues("github.com/owner/repo", 5)

        assert children == []

    def test_get_child_issues_uses_sub_issues_header(self, github_client):
        """Test that get_child_issues sends the sub_issues header."""
        mock_response = {"data": {"repository": {"issue": {"subIssues": {"nodes": []}}}}}

        with patch.object(
            github_client, "_execute_graphql_query_with_headers", return_value=mock_response
        ) as mock_query:
            github_client.get_child_issues("github.com/owner/repo", 5)

            # Verify sub_issues header is passed via kwargs
            call_kwargs = mock_query.call_args
            headers = call_kwargs.kwargs.get("headers", [])
            assert "GraphQL-Features: sub_issues" in headers


@pytest.mark.unit
class TestGetPrHeadSha:
    """Tests for GitHubTicketClient.get_pr_head_sha() method."""

    def test_get_pr_head_sha_returns_sha(self, github_client):
        """Test that get_pr_head_sha returns the HEAD SHA."""
        mock_response = {"data": {"repository": {"pullRequest": {"headRefOid": "abc123def456"}}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha == "abc123def456"

    def test_get_pr_head_sha_returns_none_when_no_pr(self, github_client):
        """Test that get_pr_head_sha returns None when PR not found."""
        mock_response = {"data": {"repository": {"pullRequest": None}}}

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha is None

    def test_get_pr_head_sha_returns_none_on_error(self, github_client):
        """Test that get_pr_head_sha returns None on API errors."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            sha = github_client.get_pr_head_sha("github.com/owner/repo", 42)

        assert sha is None


@pytest.mark.unit
class TestSetCommitStatus:
    """Tests for GitHubTicketClient.set_commit_status() method."""

    def test_set_commit_status_success(self, github_client):
        """Test that set_commit_status calls the correct API."""
        with patch.object(github_client, "_run_gh_command", return_value="{}") as mock_cmd:
            result = github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="success",
                context="kiln/child-issues",
                description="All children resolved",
            )

        assert result is True
        call_args = mock_cmd.call_args[0][0]
        assert "repos/owner/repo/statuses/abc123" in call_args
        assert "-X" in call_args
        assert "POST" in call_args
        assert "state=success" in " ".join(call_args)
        assert "context=kiln/child-issues" in " ".join(call_args)

    def test_set_commit_status_with_target_url(self, github_client):
        """Test that set_commit_status includes target_url when provided."""
        with patch.object(github_client, "_run_gh_command", return_value="{}") as mock_cmd:
            github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="pending",
                context="kiln/child-issues",
                description="1 child still open",
                target_url="https://example.com/details",
            )

        call_args = mock_cmd.call_args[0][0]
        assert "target_url=https://example.com/details" in " ".join(call_args)

    def test_set_commit_status_returns_false_on_error(self, github_client):
        """Test that set_commit_status returns False on API errors."""
        with patch.object(github_client, "_run_gh_command", side_effect=Exception("API error")):
            result = github_client.set_commit_status(
                repo="github.com/owner/repo",
                sha="abc123",
                state="success",
                context="kiln/child-issues",
                description="All resolved",
            )

        assert result is False


@pytest.mark.unit
class TestGetTicketLabels:
    """Tests for GitHubTicketClient.get_ticket_labels() method."""

    def test_get_ticket_labels_returns_label_set(self, github_client):
        """Test that get_ticket_labels returns a set of label names."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [
                                {"name": "yolo"},
                                {"name": "research_ready"},
                                {"name": "bug"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("github.com/owner/repo", 42)

        assert isinstance(labels, set)
        assert labels == {"yolo", "research_ready", "bug"}

    def test_get_ticket_labels_empty_labels(self, github_client):
        """Test handling issue with no labels."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": []
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("github.com/owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_nonexistent_issue(self, github_client):
        """Test handling nonexistent issue returns empty set."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": None
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("github.com/owner/repo", 99999)

        assert labels == set()

    def test_get_ticket_labels_handles_api_error(self, github_client):
        """Test that API errors return empty set."""
        with patch.object(
            github_client, "_execute_graphql_query", side_effect=Exception("API error")
        ):
            labels = github_client.get_ticket_labels("github.com/owner/repo", 42)

        assert labels == set()

    def test_get_ticket_labels_handles_null_nodes(self, github_client):
        """Test handling of null entries in label nodes."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {
                            "nodes": [
                                {"name": "valid-label"},
                                None,  # Can occur with deleted labels
                                {"name": "another-label"},
                            ]
                        }
                    }
                }
            }
        }

        with patch.object(github_client, "_execute_graphql_query", return_value=mock_response):
            labels = github_client.get_ticket_labels("github.com/owner/repo", 42)

        assert labels == {"valid-label", "another-label"}

    def test_get_ticket_labels_makes_correct_api_call(self, github_client):
        """Test that the correct GraphQL query is made."""
        mock_response = {
            "data": {
                "repository": {
                    "issue": {
                        "labels": {"nodes": []}
                    }
                }
            }
        }

        with patch.object(
            github_client, "_execute_graphql_query", return_value=mock_response
        ) as mock_query:
            github_client.get_ticket_labels("github.com/test-owner/test-repo", 123)

            call_args = mock_query.call_args
            query = call_args[0][0]
            variables = call_args[0][1]

            assert "repository(owner: $owner, name: $repo)" in query
            assert "issue(number: $issueNumber)" in query
            assert "labels(first: 100)" in query
            assert variables["owner"] == "test-owner"
            assert variables["repo"] == "test-repo"
            assert variables["issueNumber"] == 123


@pytest.fixture
def enterprise_318_client():
    """Fixture providing a GitHubEnterprise318Client instance."""
    return GitHubEnterprise318Client(tokens={"github.mycompany.com": "test-token"})


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
